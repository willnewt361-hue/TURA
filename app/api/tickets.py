"""Ticket endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, require_trip_assignment
from app.db.models import Ticket, User
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room, trip_room
from app.services.ticket_service import qr_png_bytes, ticket_public_view, validate_ticket
from app.security.signing import verify_ticket_token

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _authorize_ticket_access(ticket: Ticket, user: User, db: Session) -> None:
    if user.role == "driver":
        require_trip_assignment(db, ticket.booking.trip_id, user)
    elif ticket.booking.user_id != user.id and user.role not in ("operator", "admin"):
        raise HTTPException(403, "Not your ticket")


@router.get("/mine")
def my_tickets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.db.models import Booking

    tickets = (
        db.query(Ticket)
        .join(Booking, Ticket.booking_id == Booking.id)
        .filter(Booking.user_id == user.id)
        .order_by(Ticket.issued_at.desc())
        .all()
    )
    return {"tickets": [ticket_public_view(t) for t in tickets]}


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    _authorize_ticket_access(ticket, user, db)
    return {"ticket": ticket_public_view(ticket)}


@router.get("/{ticket_id}/qr.png")
def ticket_qr(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    _authorize_ticket_access(ticket, user, db)
    png = qr_png_bytes(ticket.signed_payload)
    return Response(content=png, media_type="image/png")


class ValidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=4096)


@router.post("/validate")
async def validate(
    body: ValidateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    if user.role == "driver":
        signature_valid, payload, reason = verify_ticket_token(body.token.strip())
        if payload and (signature_valid or reason == "Ticket expired"):
            require_trip_assignment(db, int(payload["trip_id"]), user)
    try:
        result = validate_ticket(db, token=body.token.strip(), actor_id=user.id)
    except HTTPException as exc:
        if exc.detail == "Invalid signature":
            db.commit()
        raise
    db.commit()
    if result.get("valid") and not result.get("offline"):
        trip_id = result.get("trip_id")
        await manager.broadcast(ops_room(), events.TICKET_VALIDATED, result)
        if trip_id:
            await manager.broadcast(
                trip_room(trip_id),
                events.TICKET_VALIDATED,
                {"trip_id": trip_id, "updated": True},
            )
    return result


@router.get("/by-no/{ticket_no}")
def by_no(ticket_no: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    _authorize_ticket_access(ticket, user, db)
    return {"ticket": ticket_public_view(ticket)}
