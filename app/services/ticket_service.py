"""Ticket issue, QR generation, validation."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

import qrcode
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Booking, Ticket
from app.security.signing import (
    default_ticket_expiry,
    make_ticket_no,
    sign_ticket_payload,
    verify_ticket_token,
)
from app.services.audit import audit


def issue_ticket(db: Session, booking: Booking, actor_id: int) -> Ticket:
    if booking.ticket:
        return booking.ticket
    if booking.status != "paid":
        raise HTTPException(400, "Booking must be paid before ticket issue")

    seq = (db.query(Ticket).count() or 0) + 1
    ticket_no = make_ticket_no(seq)
    issued = datetime.utcnow()
    expires = default_ticket_expiry()
    # Create stub then sign with real id
    ticket = Ticket(
        ticket_no=ticket_no,
        booking_id=booking.id,
        signed_payload="",
        issued_at=issued,
        expires_at=expires,
        status="valid",
    )
    db.add(ticket)
    db.flush()

    payload = {
        "ticket_id": ticket.id,
        "ticket_no": ticket_no,
        "trip_id": booking.trip_id,
        "seat_id": booking.seat_id,
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "version": 1,
    }
    ticket.signed_payload = sign_ticket_payload(payload)
    booking.status = "paid"
    audit(
        db,
        "ticket.issued",
        actor_id=actor_id,
        entity_type="ticket",
        entity_id=str(ticket.id),
        metadata={"ticket_no": ticket_no},
    )
    db.flush()
    return ticket


def qr_png_bytes(token: str) -> bytes:
    img = qrcode.make(token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def validate_ticket(
    db: Session,
    *,
    token: str,
    actor_id: int,
) -> dict:
    ok, body, reason = verify_ticket_token(token)
    if not ok and reason == "Invalid signature":
        audit(db, "ticket.validation_failed", actor_id=actor_id, metadata={"reason": reason})
        raise HTTPException(400, reason)
    if not body:
        raise HTTPException(400, reason)

    ticket = db.get(Ticket, body["ticket_id"])
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if ticket.status == "cancelled":
        raise HTTPException(400, "Ticket cancelled")
    if ticket.status == "used":
        return {
            "valid": False,
            "message": "Ticket already validated",
            "ticket_no": ticket.ticket_no,
            "validated_at": ticket.validated_at.isoformat() if ticket.validated_at else None,
        }

    if datetime.utcnow() > ticket.expires_at or reason == "Ticket expired":
        ticket.status = "expired"
        audit(
            db,
            "ticket.validation_failed",
            actor_id=actor_id,
            entity_type="ticket",
            entity_id=str(ticket.id),
            metadata={"reason": "Ticket expired"},
        )
        db.flush()
        return {
            "valid": False,
            "offline": False,
            "message": "Ticket expired",
            "ticket_no": ticket.ticket_no,
        }

    if not ok:
        raise HTTPException(400, reason)

    ticket.status = "used"
    ticket.validated_at = datetime.utcnow()
    ticket.validated_by = actor_id
    booking = ticket.booking
    if booking:
        booking.status = "completed"
    audit(
        db,
        "ticket.validated",
        actor_id=actor_id,
        entity_type="ticket",
        entity_id=str(ticket.id),
        metadata={"ticket_no": ticket.ticket_no},
    )
    db.flush()
    seat_label = booking.seat.label if booking and booking.seat else ""
    return {
        "valid": True,
        "offline": False,
        "message": "Ticket accepted",
        "ticket_no": ticket.ticket_no,
        "seat": seat_label,
        "passenger": booking.passenger_name if booking else "",
        "trip_id": booking.trip_id if booking else body["trip_id"],
    }


def ticket_public_view(ticket: Ticket) -> dict:
    booking = ticket.booking
    trip = booking.trip if booking else None
    route = trip.route if trip else None
    status = ticket.status
    if status == "valid" and datetime.utcnow() > ticket.expires_at:
        status = "expired"
    return {
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "status": status,
        "issued_at": ticket.issued_at.isoformat(),
        "expires_at": ticket.expires_at.isoformat(),
        "qr_token": ticket.signed_payload,
        "seat": booking.seat.label if booking and booking.seat else "",
        "passenger_name": booking.passenger_name if booking else "",
        "route": f"{route.origin} → {route.destination}" if route else "",
        "origin": route.origin if route else "",
        "destination": route.destination if route else "",
        "departure": trip.departure.isoformat() if trip else "",
        "arrival": trip.arrival.isoformat() if trip else "",
        "stops": [stop for stop in route.stops.split(",") if stop] if route and route.stops else [],
        "operator": trip.bus.operator if trip and trip.bus else "",
        "trip_id": booking.trip_id if booking else None,
        "booking_id": booking.id if booking else None,
    }
