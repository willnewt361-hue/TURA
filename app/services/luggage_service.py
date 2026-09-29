"""Luggage chain of custody."""

from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Booking, Luggage
from app.services.audit import audit

VALID_TRANSITIONS = {
    "registered": {"loaded", "lost"},
    "loaded": {"received", "lost"},
    "received": {"claimed", "lost"},
    "claimed": set(),
    "lost": {"received"},
}


def register_luggage(db: Session, booking: Booking, description: str, actor_id: int) -> Luggage:
    if booking.luggage:
        return booking.luggage
    tag = f"LUG-{secrets.token_hex(4).upper()}"
    lug = Luggage(
        booking_id=booking.id,
        tag_id=tag,
        fee=booking.luggage_ugx,
        status="registered",
        description=description[:255] if description else "",
    )
    db.add(lug)
    audit(db, "luggage.registered", actor_id=actor_id, entity_type="luggage", entity_id=tag)
    db.flush()
    return lug


def scan_luggage(db: Session, tag_id: str, new_status: str, actor_id: int) -> Luggage:
    lug = db.query(Luggage).filter(Luggage.tag_id == tag_id).first()
    if not lug:
        raise HTTPException(404, "Luggage tag not found")
    allowed = VALID_TRANSITIONS.get(lug.status, set())
    if new_status not in allowed:
        raise HTTPException(400, f"Cannot move luggage from {lug.status} to {new_status}")
    lug.status = new_status
    lug.updated_at = datetime.utcnow()
    audit(
        db,
        "luggage.scanned",
        actor_id=actor_id,
        entity_type="luggage",
        entity_id=tag_id,
        metadata={"status": new_status},
    )
    db.flush()
    return lug
