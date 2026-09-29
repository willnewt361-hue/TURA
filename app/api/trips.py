"""Trip search, seats, tracking endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import (
    get_current_user,
    get_optional_user,
    require_roles,
    require_trip_assignment,
)
from app.db.models import Booking, Route, Trip, User
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room, trip_room
from app.services import booking_service, tracking_service

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _trip_out(trip: Trip, available: Optional[int] = None) -> dict:
    amenities = trip.bus.amenities.split(",") if trip.bus else []
    return {
        "id": trip.id,
        "departure": trip.departure.isoformat(),
        "arrival": trip.arrival.isoformat(),
        "status": trip.status,
        "fare_ugx": trip.fare_ugx,
        "origin": trip.route.origin,
        "destination": trip.route.destination,
        "stops": trip.route.stops.split(",") if trip.route.stops else [],
        "duration_minutes": trip.route.duration_minutes,
        "operator": trip.bus.operator,
        "plate": trip.bus.plate,
        "rating": trip.bus.rating,
        "amenities": amenities,
        "available_seats": available,
        "bus_id": trip.bus_id,
        "route_id": trip.route_id,
    }


@router.get("/cities")
def cities(db: Session = Depends(get_db)):
    origins = [r[0] for r in db.query(Route.origin).distinct().all()]
    dests = [r[0] for r in db.query(Route.destination).distinct().all()]
    return {"origins": sorted(set(origins)), "destinations": sorted(set(dests))}


@router.get("/popular")
def popular(db: Session = Depends(get_db)):
    routes = db.query(Route).limit(8).all()
    return {
        "routes": [
            {
                "id": r.id,
                "origin": r.origin,
                "destination": r.destination,
                "fare_ugx": r.base_fare_ugx,
                "image_slug": r.image_slug,
                "distance_km": r.distance_km,
            }
            for r in routes
        ]
    }


@router.get("/search")
def search(
    origin: str = Query(..., min_length=2),
    destination: str = Query(..., min_length=2),
    date: Optional[str] = None,
    sort: str = "price",
    db: Session = Depends(get_db),
):
    origin = origin.strip()
    destination = destination.strip()
    if origin.lower() == destination.lower():
        raise HTTPException(400, "Origin and destination must differ")

    q = (
        db.query(Trip)
        .join(Route)
        .options(joinedload(Trip.bus), joinedload(Trip.route))
        .filter(
            Route.origin.ilike(origin),
            Route.destination.ilike(destination),
            Trip.active.is_(True),
            Trip.status != "cancelled",
        )
    )
    if date:
        try:
            day = datetime.fromisoformat(date).date()
        except ValueError as exc:
            raise HTTPException(400, "Invalid date — use YYYY-MM-DD") from exc
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        q = q.filter(Trip.departure >= start, Trip.departure < end)
    else:
        q = q.filter(Trip.departure >= datetime.utcnow() - timedelta(hours=1))

    trips = q.order_by(Trip.departure).all()
    if sort == "price":
        trips = sorted(trips, key=lambda t: t.fare_ugx)
    elif sort == "time":
        trips = sorted(trips, key=lambda t: t.departure)

    out = []
    for trip in trips:
        seats = booking_service.seat_status_map(db, trip.id)
        available = sum(1 for s in seats if s["status"] == "available")
        out.append(_trip_out(trip, available))
    return {"trips": out, "count": len(out)}


@router.get("/{trip_id}")
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.bus), joinedload(Trip.route))
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(404, "Trip not found")
    seats = booking_service.seat_status_map(db, trip.id)
    available = sum(1 for s in seats if s["status"] == "available")
    return {"trip": _trip_out(trip, available)}


@router.get("/{trip_id}/seats")
def seats(
    trip_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    return {"seats": booking_service.seat_status_map(db, trip_id, viewer_id=user.id if user else None)}


class LockIn(BaseModel):
    seat_id: int


@router.post("/{trip_id}/seats/lock")
async def lock_seat(
    trip_id: int,
    body: LockIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lock = booking_service.lock_seat(db, trip_id, body.seat_id, user.id)
    db.commit()
    await manager.broadcast(
        trip_room(trip_id),
        events.SEAT_LOCKED,
        {"trip_id": trip_id, "seat_id": body.seat_id, "expires_at": lock.expires_at.isoformat()},
    )
    return {"ok": True, "expires_at": lock.expires_at.isoformat(), "seats": booking_service.seat_status_map(db, trip_id, user.id)}


@router.post("/{trip_id}/seats/{seat_id}/release")
async def release_seat(
    trip_id: int,
    seat_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ok = booking_service.release_seat(db, trip_id, seat_id, user.id)
    db.commit()
    if ok:
        await manager.broadcast(
            trip_room(trip_id),
            events.SEAT_RELEASED,
            {"trip_id": trip_id, "seat_id": seat_id},
        )
    return {"ok": ok, "seats": booking_service.seat_status_map(db, trip_id, user.id)}


@router.get("/{trip_id}/tracking")
def tracking(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    if user.role == "driver":
        require_trip_assignment(db, trip_id, user)
    elif user.role == "customer":
        booking = (
            db.query(Booking.id)
            .filter(
                Booking.user_id == user.id,
                Booking.trip_id == trip_id,
                Booking.status.in_(["paid", "completed"]),
            )
            .first()
        )
        if not booking:
            raise HTTPException(403, "Live tracking is available to booked passengers")
    elif user.role not in {"operator", "admin"}:
        raise HTTPException(403, "Live tracking access denied")
    return {
        "position": tracking_service.latest_position(db, trip_id),
        "status": trip.status,
        "replay": tracking_service.replay_points(db, trip_id),
        "waypoints": [
            {"lat": a, "lng": b, "label": c}
            for a, b, c in tracking_service.waypoints_for_trip(trip)
        ],
    }


@router.post("/{trip_id}/tracking/advance")
async def advance_tracking(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    require_trip_assignment(db, trip_id, user)
    point = tracking_service.advance_tracking(db, trip_id, actor_id=user.id)
    trip = db.get(Trip, trip_id)
    db.commit()
    data = {
        "trip_id": trip_id,
        "lat": point.lat,
        "lng": point.lng,
        "label": point.label,
        "progress_pct": point.progress_pct,
        "status": trip.status,
        "timestamp": point.timestamp.isoformat(),
    }
    await manager.broadcast(trip_room(trip_id), events.TRIP_POSITION, data)
    await manager.broadcast(ops_room(), events.TRIP_POSITION, data)
    return data


@router.get("/{trip_id}/passengers")
def passengers(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    require_trip_assignment(db, trip_id, user)
    bookings = (
        db.query(Booking)
        .filter(Booking.trip_id == trip_id, Booking.status.in_(["paid", "completed"]))
        .all()
    )
    return {
        "passengers": [
            {
                "booking_id": b.id,
                "name": b.passenger_name,
                "phone": b.passenger_phone[-4:].rjust(len(b.passenger_phone), "*") if b.passenger_phone else "",
                "seat": b.seat.label if b.seat else "",
                "ticket_no": b.ticket.ticket_no if b.ticket else None,
                "ticket_status": b.ticket.status if b.ticket else None,
            }
            for b in bookings
        ]
    }
