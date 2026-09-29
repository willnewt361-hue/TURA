"""SOS alerts — demo/local only, no fake police dispatch."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import SOSAlert
from app.services.audit import audit


def create_sos(
    db: Session,
    *,
    user_id: int,
    trip_id: Optional[int],
    reason: str,
    location: str = "",
    sos_type: str = "private_operational",
) -> SOSAlert:
    if not reason.strip():
        raise HTTPException(400, "Reason is required")
    alert = SOSAlert(
        user_id=user_id,
        trip_id=trip_id,
        sos_type=sos_type,
        reason=reason.strip()[:500],
        location=location[:160],
        status="open",
        demo_note="Demo/Local alert",
    )
    db.add(alert)
    db.flush()
    audit(
        db,
        "sos.created",
        actor_id=user_id,
        entity_type="sos",
        entity_id=str(alert.id),
        metadata={"type": sos_type, "demo": True},
    )
    return alert


def acknowledge_sos(db: Session, alert_id: int, actor_id: int) -> SOSAlert:
    alert = db.get(SOSAlert, alert_id)
    if not alert:
        raise HTTPException(404, "SOS not found")
    alert.status = "acknowledged"
    alert.acknowledged_by = actor_id
    alert.acknowledged_at = datetime.utcnow()
    audit(db, "sos.acknowledged", actor_id=actor_id, entity_type="sos", entity_id=str(alert_id))
    db.flush()
    return alert
