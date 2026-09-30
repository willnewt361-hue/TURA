"""TURA FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import __version__
from app.api import auth, bookings, luggage, operations, payments, reports, sos, tickets, trips
from app.api.deps import COOKIE_NAME, decode_token
from app.config import get_google_maps_api_key, get_settings
from app.db.models import Booking, Trip, User
from app.db.seed import seed_if_empty
from app.db.session import SessionLocal, init_db
from app.realtime.manager import manager, ops_room, trip_room
from app.security.middleware import (
    CSRFMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.services import booking_service

FRONTEND = ROOT / "frontend"
logger = logging.getLogger(__name__)
TRIP_ROOM = re.compile(r"^trip:(\d{1,18})$")
DRIVER_ROOM = re.compile(r"^driver:(\d{1,18})$")


def _websocket_user(websocket: WebSocket) -> User | None:
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        authorization = websocket.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (HTTPException, KeyError, TypeError, ValueError):
        return None
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        return user if user and user.status == "active" else None
    finally:
        db.close()


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    settings = get_settings()
    if origin in settings.cors_origin_list:
        return True
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    host = websocket.headers.get("host", "").lower()
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host


def _can_join_room(room: str, user: User, db: Session) -> bool:
    if room == ops_room():
        return user.role in {"operator", "admin"}

    trip_match = TRIP_ROOM.fullmatch(room)
    driver_match = DRIVER_ROOM.fullmatch(room)
    match = trip_match or driver_match
    if not match:
        return False
    trip = db.get(Trip, int(match.group(1)))
    if not trip:
        return False
    if driver_match:
        return user.role in {"admin", "operator"} or (
            user.role == "driver" and trip.driver_id == user.id
        )
    if user.role in {"admin", "operator"}:
        return True
    if user.role == "driver":
        return trip.driver_id == user.id
    if user.role == "customer":
        return (
            db.query(Booking.id)
            .filter(
                Booking.user_id == user.id,
                Booking.trip_id == trip.id,
                Booking.status.in_(["paid", "completed"]),
            )
            .first()
            is not None
        )
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()

    async def lock_sweeper():
        while True:
            await asyncio.sleep(30)
            db = SessionLocal()
            try:
                released = booking_service.purge_expired_locks(db)
                db.commit()
                for item in released:
                    await manager.broadcast(
                        trip_room(item["trip_id"]),
                        "seat.released",
                        {"trip_id": item["trip_id"], "seat_id": item["seat_id"]},
                    )
            except Exception:
                db.rollback()
                logger.exception("Failed to sweep expired seat locks")
            finally:
                db.close()

    task = asyncio.create_task(lock_sweeper())
    yield
    task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="TURA",
        description="Offline-First Bus Travel WebSocket App",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-CSRF-Token"],
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(CSRFMiddleware)

    application.include_router(auth.router)
    application.include_router(operations.router)
    application.include_router(trips.router)
    application.include_router(bookings.router)
    application.include_router(payments.router)
    application.include_router(tickets.router)
    application.include_router(luggage.router)
    application.include_router(sos.router)
    application.include_router(reports.router)

    @application.get("/api/ping")
    def ping():
        return {"ok": True, "version": __version__, "tagline": "One Tap, One Journey."}

    @application.get("/api/config")
    def public_config():
        current = get_settings()
        return {
            "fees": current.fee_config(),
            "features": current.feature_flags(),
            "currency": current.currency,
            "demo_mode": current.demo_mode,
            "seat_lock_seconds": current.seat_lock_seconds,
            "google_maps_api_key": get_google_maps_api_key(),
        }

    @application.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        if not _websocket_origin_allowed(websocket):
            await websocket.close(code=4403)
            return
        user = _websocket_user(websocket)
        if not user:
            await websocket.close(code=4401)
            return

        rooms_q = websocket.query_params.get("rooms", "")
        if len(rooms_q) > 1024:
            await websocket.close(code=4403)
            return
        requested_rooms = list(dict.fromkeys(r.strip() for r in rooms_q.split(",") if r.strip()))
        if len(requested_rooms) > 10:
            await websocket.close(code=4403)
            return
        db = SessionLocal()
        try:
            if not all(_can_join_room(room, user, db) for room in requested_rooms):
                await websocket.close(code=4403)
                return
        finally:
            db.close()

        await manager.connect(websocket, requested_rooms, user_id=user.id)
        message_window = monotonic()
        message_count = 0
        try:
            await websocket.send_text(
                json.dumps({"event": "connected", "data": {"rooms": requested_rooms}})
            )
            while True:
                now = monotonic()
                if now - message_window >= 60:
                    message_window = now
                    message_count = 0
                message_count += 1
                if message_count > 120:
                    await websocket.close(code=1008)
                    break
                msg = await websocket.receive_text()
                if len(msg) > 2048:
                    await websocket.close(code=1009)
                    break
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    await websocket.send_text(
                        json.dumps({"event": "error", "data": {"detail": "Invalid message"}})
                    )
                    continue
                if not isinstance(data, dict):
                    await websocket.send_text(
                        json.dumps({"event": "error", "data": {"detail": "Invalid message"}})
                    )
                    continue
                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
                elif data.get("type") == "subscribe":
                    room = data.get("room")
                    if not isinstance(room, str) or len(room) > 64:
                        await websocket.send_text(
                            json.dumps({"event": "error", "data": {"detail": "Invalid room"}})
                        )
                        continue
                    db = SessionLocal()
                    try:
                        current_user = db.get(User, user.id)
                        allowed = (
                            current_user is not None
                            and current_user.status == "active"
                            and current_user.role == user.role
                            and _can_join_room(room, current_user, db)
                        )
                    finally:
                        db.close()
                    if not allowed:
                        await websocket.send_text(
                            json.dumps({"event": "error", "data": {"detail": "Room access denied"}})
                        )
                        continue
                    if room not in requested_rooms and len(requested_rooms) >= 10:
                        await websocket.send_text(
                            json.dumps({"event": "error", "data": {"detail": "Room limit reached"}})
                        )
                        continue
                    manager.rooms.setdefault(room, set()).add(websocket)
                    if room not in requested_rooms:
                        requested_rooms.append(room)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("WebSocket connection failed")
        finally:
            manager.disconnect(websocket)

    assets = FRONTEND / "assets"
    css = FRONTEND / "css"
    js = FRONTEND / "js"
    pages = FRONTEND / "pages"
    screen_gallery = ROOT / "TURA"
    if assets.exists():
        application.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
    if css.exists():
        application.mount("/css", StaticFiles(directory=str(css)), name="css")
    if js.exists():
        application.mount("/js", StaticFiles(directory=str(js)), name="js")
    if pages.exists():
        application.mount("/pages", StaticFiles(directory=str(pages)), name="pages")
    if screen_gallery.exists():
        application.mount(
            "/screens",
            StaticFiles(directory=str(screen_gallery), html=True),
            name="screen-gallery",
        )
    elif (ROOT / "Master.jpg").is_file():
        gallery_files = {
            "Master.jpg",
            "Splash screen..jpg",
            "Home screen.jpg",
            "2nd page.jpg",
            "3rd.jpg",
            "4th.jpg",
            "5th.jpg",
            "6th.jpg",
            "7th.jpg",
            "8th.jpg",
            "9th.jpg",
            "index.html",
            "splash.html",
            "home.html",
            "buses.html",
            "seats.html",
            "passenger.html",
            "payment.html",
            "ticket.html",
            "tracking.html",
            "tickets.html",
            "explore.html",
            "screens.css",
            "screens.js",
        }

        @application.get("/screens/")
        def screen_gallery_index():
            return FileResponse(ROOT / "index.html")

        @application.get("/screens/{asset_name}")
        def screen_gallery_asset(asset_name: str):
            if asset_name not in gallery_files:
                raise HTTPException(status_code=404, detail="Gallery asset not found")
            return FileResponse(ROOT / asset_name)

    @application.get("/")
    def index():
        return FileResponse(FRONTEND / "pages" / "index.html")

    @application.get("/app")
    @application.get("/app/")
    def connected_app():
        return FileResponse(FRONTEND / "index.html")

    @application.get("/sw.js")
    def service_worker():
        return FileResponse(FRONTEND / "sw.js", media_type="application/javascript")

    @application.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(FRONTEND / "manifest.webmanifest", media_type="application/manifest+json")

    @application.get("/favicon.ico")
    def favicon():
        logo = FRONTEND / "assets" / "logo.svg"
        return FileResponse(logo) if logo.exists() else RedirectResponse("/")

    @application.get("/api/health")
    def health_public():
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Public health check database query failed")
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "version": __version__},
            )
        finally:
            db.close()
        return {"status": "ok", "version": __version__}

    return application


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    import uvicorn

    host = "0.0.0.0" if os.environ.get("PORT") else settings.host
    uvicorn.run(app, host=host, port=int(os.environ.get("PORT", settings.port)))
