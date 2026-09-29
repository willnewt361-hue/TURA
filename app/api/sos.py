"""SOS endpoints — demo/local alerts only."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, require_trip_assignment
from app.config import get_settings
from app.db.models import Booking, SOSAlert, Trip, User
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room, trip_room
from app.services.sos_service import acknowledge_sos, create_sos
router = APIRouter(prefix="/api/sos", tags=["sos"])


class SOSIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    trip_id: Optional[int] = Field(default=None, gt=0)
    location: str = Field(default="", max_length=160)
    sos_type: Literal["private_operational"] = "private_operational"


@router.post("")
async def create(
    body: SOSIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not get_settings().feature_sos:
        raise HTTPException(403, "SOS feature disabled")
    if body.trip_id is not None:
        trip = db.get(Trip, body.trip_id)
        if not trip:
            raise HTTPException(404, "Trip not found")
        if user.role == "driver":
            require_trip_assignment(db, body.trip_id, user)
        elif user.role == "customer":
            booking = (
                db.query(Booking)
                .filter(
                    Booking.user_id == user.id,
                    Booking.trip_id == body.trip_id,
                    Booking.status.in_(["paid", "completed"]),
                )
                .first()
            )
            if not booking:
                raise HTTPException(403, "SOS trip must belong to one of your bookings")
    alert = create_sos(
        db,
        user_id=user.id,
        trip_id=body.trip_id,
        reason=body.reason,
        location=body.location,
        sos_type=body.sos_type,
    )
    db.commit()
    data = {
        "id": alert.id,
        "reason": alert.reason,
        "location": alert.location,
        "status": alert.status,
        "demo_note": alert.demo_note,
        "trip_id": alert.trip_id,
        "created_at": alert.created_at.isoformat(),
    }
    await manager.broadcast(ops_room(), events.SOS_CREATED, data)
    if alert.trip_id:
        await manager.broadcast(
            trip_room(alert.trip_id),
            events.SOS_CREATED,
            {"id": alert.id, "trip_id": alert.trip_id, "status": alert.status},
        )
    return {"alert": data, "notice": "Demo/Local alert — police dispatch is NOT simulated."}


@router.get("")
def list_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    query = db.query(SOSAlert)
    if user.role == "driver":
        query = query.join(Trip, SOSAlert.trip_id == Trip.id).filter(Trip.driver_id == user.id)
    alerts = query.order_by(SOSAlert.created_at.desc()).limit(50).all()
    return {
        "alerts": [
            {
                "id": a.id,
                "reason": a.reason,
                "location": a.location,
                "status": a.status,
                "demo_note": a.demo_note,
                "trip_id": a.trip_id,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
    }


@router.post("/{alert_id}/acknowledge")
async def ack(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    alert = db.get(SOSAlert, alert_id)
    if user.role == "driver" and (not alert or alert.trip_id is None):
        raise HTTPException(403, "Driver can only acknowledge alerts for assigned trips")
    if user.role == "driver":
        require_trip_assignment(db, alert.trip_id, user)
    alert = acknowledge_sos(db, alert_id, user.id)
    db.commit()
    data = {"id": alert.id, "status": alert.status}
    await manager.broadcast(ops_room(), events.SOS_ACKNOWLEDGED, data)
    return data
