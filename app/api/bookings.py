"""Booking endpoints."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_trip_assignment
from app.db.models import Booking, Trip, User
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room, trip_room
from app.services import booking_service
from app.services.payment_service import new_idempotency_key

router = APIRouter(prefix="/api/bookings", tags=["bookings"])
PHONE_RE = re.compile(r"^\+?\d{9,15}$")


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_id: int
    seat_id: int
    passenger_name: str = Field(min_length=2, max_length=120)
    passenger_phone: str = Field(min_length=9, max_length=32)
    passenger_email: Optional[str] = Field(default=None, max_length=160)
    special_request: Optional[str] = Field(default=None, max_length=500)
    include_insurance: bool = False
    include_luggage: bool = False
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=64)
    client_operation_id: Optional[str] = Field(default=None, min_length=8, max_length=64)


def _booking_out(b: Booking) -> dict:
    trip = b.trip
    route = trip.route if trip else None
    return {
        "id": b.id,
        "status": b.status,
        "trip_id": b.trip_id,
        "seat_id": b.seat_id,
        "seat": b.seat.label if b.seat else "",
        "passenger_name": b.passenger_name,
        "passenger_phone": b.passenger_phone,
        "passenger_email": b.passenger_email,
        "special_request": b.special_request,
        "fare_ugx": b.fare_ugx,
        "insurance_ugx": b.insurance_ugx,
        "luggage_ugx": b.luggage_ugx,
        "booking_fee_ugx": b.booking_fee_ugx,
        "total_ugx": b.total_ugx,
        "include_insurance": b.include_insurance,
        "include_luggage": b.include_luggage,
        "created_at": b.created_at.isoformat(),
        "origin": route.origin if route else "",
        "destination": route.destination if route else "",
        "departure": trip.departure.isoformat() if trip else "",
        "arrival": trip.arrival.isoformat() if trip else "",
        "operator": trip.bus.operator if trip and trip.bus else "",
        "ticket_id": b.ticket.id if b.ticket else None,
        "ticket_no": b.ticket.ticket_no if b.ticket else None,
        "ticket_status": b.ticket.status if b.ticket else None,
    }


def _load_booking(db: Session, booking_id: int) -> Optional[Booking]:
    return (
        db.query(Booking)
        .options(
            joinedload(Booking.trip).joinedload(Trip.route),
            joinedload(Booking.trip).joinedload(Trip.bus),
            joinedload(Booking.seat),
            joinedload(Booking.ticket),
        )
        .filter(Booking.id == booking_id)
        .first()
    )


@router.post("")
async def create_booking(
    body: BookingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not PHONE_RE.match(body.passenger_phone.strip()):
        raise HTTPException(400, "Invalid passenger phone")
    name = re.sub(r"[<>]", "", body.passenger_name).strip()
    if len(name) < 2:
        raise HTTPException(400, "Passenger name must contain at least two characters")
    special = re.sub(r"[<>]", "", body.special_request or "").strip() or None
    key = body.idempotency_key or new_idempotency_key()
    booking = booking_service.create_booking(
        db,
        user_id=user.id,
        trip_id=body.trip_id,
        seat_id=body.seat_id,
        passenger_name=name,
        passenger_phone=body.passenger_phone.strip(),
        passenger_email=body.passenger_email,
        special_request=special,
        include_insurance=body.include_insurance,
        include_luggage=body.include_luggage,
        idempotency_key=key,
        client_operation_id=body.client_operation_id,
    )
    db.commit()
    booking = _load_booking(db, booking.id)
    await manager.broadcast(
        trip_room(body.trip_id),
        events.SEAT_BOOKED,
        {"trip_id": body.trip_id, "seat_id": body.seat_id},
    )
    await manager.broadcast(ops_room(), events.BOOKING_UPDATED, {"booking_id": booking.id})
    return {"booking": _booking_out(booking)}


@router.get("/fees/quote")
def quote_fees(fare_ugx: int = 40000, insurance: bool = False, luggage: bool = False):
    return booking_service.calculate_totals(fare_ugx, insurance=insurance, luggage=luggage)


@router.get("/mine")
def my_bookings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.trip).joinedload(Trip.route),
            joinedload(Booking.trip).joinedload(Trip.bus),
            joinedload(Booking.seat),
            joinedload(Booking.ticket),
        )
        .filter(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return {"bookings": [_booking_out(b) for b in bookings]}


@router.get("/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = _load_booking(db, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if user.role == "driver":
        require_trip_assignment(db, booking.trip_id, user)
    elif booking.user_id != user.id and user.role not in ("operator", "admin"):
        raise HTTPException(403, "Not your booking")
    return {"booking": _booking_out(booking)}
