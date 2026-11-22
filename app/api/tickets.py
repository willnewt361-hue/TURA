"""Ticket endpoints."""

from __future__ import annotations

import base64
import re

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


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=4096)


class LookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_no: str = Field(min_length=6, max_length=32)
    phone: str = Field(min_length=9, max_length=32)


@router.post("/lookup")
def lookup_ticket(body: LookupIn, db: Session = Depends(get_db)):
    """Recover a ticket with its number plus the phone used to book it.

    Ticket numbers are sequential, so the phone number is the second factor.
    Responses are deliberately generic to avoid confirming which part was wrong.
    """
    ticket_no = body.ticket_no.strip().upper()
    phone = re.sub(r"[\s-]", "", body.phone.strip())
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    booking = ticket.booking if ticket else None
    candidates = {
        re.sub(r"[\s-]", "", booking.passenger_phone or "") if booking else "",
        re.sub(r"[\s-]", "", booking.user.phone or "") if booking and booking.user else "",
    }
    if not ticket or phone not in candidates:
        raise HTTPException(404, "Ticket not found for that number and phone")

    view = ticket_public_view(ticket)
    view.pop("passenger_name", None)
    view["qr_data_url"] = "data:image/png;base64," + base64.b64encode(
        qr_png_bytes(ticket.signed_payload)
    ).decode("ascii")
    view["phone_hint"] = f"{phone[:5]}•••{phone[-2:]}" if len(phone) > 7 else "•••"
    return {"ticket": view}


@router.post("/verify")
def verify_public(body: VerifyIn, db: Session = Depends(get_db)):
    """Read-only verification for a scanned QR token.

    Returns no passenger contact details and never marks the ticket used.
    """
    ok, payload, reason = verify_ticket_token(body.token.strip())
    if not payload:
        return {"valid": False, "status": "invalid", "message": reason}
    ticket = db.get(Ticket, int(payload.get("ticket_id", 0)))
    if not ticket or ticket.ticket_no != payload.get("ticket_no"):
        return {"valid": False, "status": "invalid", "message": "Ticket not found"}
    if ticket.status == "used":
        return {
            "valid": False,
            "status": "used",
            "message": "Ticket already validated",
            "ticket_no": ticket.ticket_no,
            "validated_at": ticket.validated_at.isoformat() if ticket.validated_at else None,
        }
    if ticket.status == "cancelled":
        return {"valid": False, "status": "cancelled", "message": "Ticket cancelled", "ticket_no": ticket.ticket_no}
    if ticket.status == "expired" or not ok:
        return {"valid": False, "status": "expired", "message": "Ticket expired", "ticket_no": ticket.ticket_no}

    booking = ticket.booking
    trip = booking.trip if booking else None
    route = trip.route if trip else None
    return {
        "valid": True,
        "status": "valid",
        "message": "Ticket is valid and unused",
        "ticket_no": ticket.ticket_no,
        "seat": booking.seat.label if booking and booking.seat else "",
        "route": f"{route.origin} → {route.destination}" if route else "",
        "departure": trip.departure.isoformat() if trip else "",
        "expires_at": ticket.expires_at.isoformat(),
        "note": "Verification does not mark the ticket used. A driver or operator must validate it at boarding.",
    }


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
        if exc.status_code == 400:
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
