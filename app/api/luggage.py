"""Luggage endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, require_trip_assignment
from app.db.models import Luggage, User
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room
from app.services.luggage_service import scan_luggage

router = APIRouter(prefix="/api/luggage", tags=["luggage"])


class ScanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_id: str = Field(min_length=5, max_length=32)
    status: str = Field(pattern="^(loaded|received|claimed|lost)$")


@router.post("/scan")
async def scan(
    body: ScanIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    tag_id = body.tag_id.strip().upper()
    existing = db.query(Luggage).filter(Luggage.tag_id == tag_id).first()
    if existing and user.role == "driver":
        require_trip_assignment(db, existing.booking.trip_id, user)
    lug = scan_luggage(db, tag_id, body.status, user.id)
    db.commit()
    data = {"tag_id": lug.tag_id, "status": lug.status, "booking_id": lug.booking_id}
    await manager.broadcast(ops_room(), events.LUGGAGE_SCANNED, data)
    return data


@router.get("/{tag_id}")
def get_tag(tag_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lug = db.query(Luggage).filter(Luggage.tag_id == tag_id.strip().upper()).first()
    if not lug:
        raise HTTPException(404, "Not found")
    if user.role == "driver":
        require_trip_assignment(db, lug.booking.trip_id, user)
    if user.role == "customer" and lug.booking.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    return {
        "tag_id": lug.tag_id,
        "status": lug.status,
        "fee": lug.fee,
        "description": lug.description,
        "updated_at": lug.updated_at.isoformat(),
        "booking_id": lug.booking_id,
    }
