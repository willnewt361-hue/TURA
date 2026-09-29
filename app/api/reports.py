"""Operator reports, health, backup, audit."""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app import __version__
from app.config import get_settings
from app.db.models import AuditEvent, Booking, Payment, Settlement, Ticket, Trip, User
from app.db.session import get_db, engine
from app.realtime.manager import manager
from app.services.audit import audit

router = APIRouter(prefix="/api/reports", tags=["reports"])
logger = logging.getLogger(__name__)
BACKUP_RETENTION = 10


def _backup_folder() -> Path:
    database_path = engine.url.database
    if not database_path:
        raise HTTPException(503, "Database path is unavailable")
    return Path(database_path).resolve().parent / "backups"


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    revenue = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status == "success", Payment.created_at >= today)
        .scalar()
    )
    bookings_today = (
        db.query(func.count(Booking.id)).filter(Booking.created_at >= today).scalar()
    )
    tickets_valid = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.status == "valid", Ticket.expires_at > datetime.utcnow())
        .scalar()
    )
    tickets_used = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.status == "used", Ticket.validated_at >= today)
        .scalar()
    )
    active_trips = (
        db.query(func.count(Trip.id))
        .filter(Trip.status.in_(["scheduled", "boarding", "en_route"]), Trip.active.is_(True))
        .scalar()
    )

    # Last 7 days revenue chart
    chart = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        nxt = day + timedelta(days=1)
        amt = (
            db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.status == "success", Payment.created_at >= day, Payment.created_at < nxt)
            .scalar()
        )
        chart.append({"date": day.strftime("%Y-%m-%d"), "revenue": int(amt)})

    recent = (
        db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(20).all()
    )
    return {
        "kpis": {
            "revenue_today": int(revenue),
            "bookings_today": bookings_today,
            "tickets_valid": tickets_valid,
            "tickets_validated_today": tickets_used,
            "active_trips": active_trips,
        },
        "revenue_chart": chart,
        "audit": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "actor_id": e.actor_id,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in recent
        ],
    }


@router.post("/settlements/run")
def run_settlements(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    settings = get_settings()
    trips = db.query(Trip).filter(Trip.status.in_(["arrived", "en_route"])).all()
    created = []
    for trip in trips:
        existing = db.query(Settlement).filter(Settlement.trip_id == trip.id).first()
        if existing:
            continue
        gross = (
            db.query(func.coalesce(func.sum(Booking.total_ugx), 0))
            .filter(Booking.trip_id == trip.id, Booking.status.in_(["paid", "completed"]))
            .scalar()
        )
        fees = int(gross * settings.commission_pct / 100)
        s = Settlement(
            trip_id=trip.id,
            gross=int(gross),
            fees=fees,
            net=int(gross) - fees,
            provider="mock",
            status="pending",
        )
        db.add(s)
        created.append(trip.id)
    audit(
        db,
        "settlements.generated",
        actor_id=user.id,
        entity_type="settlement_batch",
        entity_id=",".join(map(str, created)),
        metadata={"trip_ids": created, "count": len(created)},
    )
    db.commit()
    return {"created_for_trips": created}


@router.get("/health")
def health(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    settings = get_settings()
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Operator health check database query failed")
        db_ok = False
    ws_clients = sum(len(v) for v in manager.rooms.values())
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "websocket_connections": ws_clients,
        "rooms": {k: len(v) for k, v in manager.rooms.items()},
        "features": settings.feature_flags(),
        "fees": settings.fee_config(),
        "version": __version__,
        "time": datetime.utcnow().isoformat(),
    }


@router.post("/backup")
def backup(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "operator")),
):
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        raise HTTPException(501, "Backup is currently supported for SQLite deployments only")
    src = Path(engine.url.database).resolve()
    if not src.is_file():
        raise HTTPException(503, "Database file is not available for backup")
    folder = _backup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    dest = folder / f"tura_{stamp}.db"
    try:
        with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
            source.backup(target)
    except sqlite3.Error as exc:
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                logger.exception("Could not remove incomplete database backup")
        raise HTTPException(503, "Database backup failed") from exc
    try:
        old_backups = sorted(
            path for path in folder.glob("tura_*.db")
            if path.is_file() and path != dest
        )
        for old in old_backups[:-BACKUP_RETENTION + 1]:
            old.unlink()
    except OSError:
        logger.exception("Could not prune old database backups")
    size_bytes = dest.stat().st_size
    audit(
        db,
        "backup.created",
        actor_id=user.id,
        entity_type="backup",
        entity_id=dest.name,
        metadata={"size_bytes": size_bytes},
    )
    db.commit()
    return {"ok": True, "name": dest.name, "size_bytes": size_bytes}


@router.get("/backup/download")
def download_latest_backup(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "operator")),
):
    folder = _backup_folder()
    if not folder.is_dir():
        raise HTTPException(404, "No backups")
    files = sorted(path for path in folder.glob("tura_*.db") if path.is_file())
    if not files:
        raise HTTPException(404, "No backups")
    path = files[-1]
    audit(
        db,
        "backup.downloaded",
        actor_id=user.id,
        entity_type="backup",
        entity_id=path.name,
    )
    db.commit()
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
