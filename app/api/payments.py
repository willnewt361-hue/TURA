"""Payment endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Booking, User
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room
from app.services.luggage_service import register_luggage
from app.services.payment_service import new_idempotency_key, process_payment
from app.services.ticket_service import issue_ticket, ticket_public_view

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_id: int = Field(gt=0)
    method: Literal["mobile_money", "card", "bank"] = "mobile_money"
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64)


@router.post("/charge")
async def charge(
    body: PayIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, body.booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.user_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your booking")

    key = body.idempotency_key or new_idempotency_key()
    payment = process_payment(db, booking, method=body.method, idempotency_key=key, actor_id=user.id)
    ticket = None
    luggage = None
    if payment.status == "success":
        ticket = issue_ticket(db, booking, actor_id=user.id)
        if booking.include_luggage:
            luggage = register_luggage(db, booking, "Passenger luggage", user.id)
    db.commit()

    await manager.broadcast(
        ops_room(),
        events.BOOKING_UPDATED,
        {"booking_id": booking.id, "payment_status": payment.status},
    )

    return {
        "payment": {
            "id": payment.id,
            "status": payment.status,
            "provider": payment.provider,
            "method": payment.method,
            "amount": payment.amount,
            "provider_ref": payment.provider_ref,
        },
        "ticket": ticket_public_view(ticket) if ticket else None,
        "luggage_tag": luggage.tag_id if luggage else None,
    }
