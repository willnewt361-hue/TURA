"""Booking and seat-lock services — server-authoritative seats."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Booking, Seat, SeatLock, Ticket, Trip
from app.services.audit import audit


def purge_expired_locks(db: Session, trip_id: Optional[int] = None) -> list[dict]:
    now = datetime.utcnow()
    q = db.query(SeatLock).filter(SeatLock.expires_at < now)
    if trip_id is not None:
        q = q.filter(SeatLock.trip_id == trip_id)
    expired = q.all()
    released = []
    for lock in expired:
        released.append({"trip_id": lock.trip_id, "seat_id": lock.seat_id, "user_id": lock.user_id})
        db.delete(lock)
    if expired:
        db.flush()
    return released


def seat_status_map(db: Session, trip_id: int, viewer_id: Optional[int] = None) -> list[dict]:
    """Return seats with live status for a trip."""
    purge_expired_locks(db, trip_id)
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    seats = db.query(Seat).filter(Seat.bus_id == trip.bus_id).order_by(Seat.row, Seat.column).all()
    locks = {l.seat_id: l for l in db.query(SeatLock).filter(SeatLock.trip_id == trip_id).all()}
    booked_seat_ids = {
        b.seat_id
        for b in db.query(Booking).filter(
            Booking.trip_id == trip_id,
            Booking.status.in_(["pending", "paid", "completed"]),
        ).all()
    }
    result = []
    for s in seats:
        status = "available"
        locked_by_me = False
        if s.status == "maintenance":
            status = "maintenance"
        elif s.id in booked_seat_ids:
            status = "occupied"
        elif s.id in locks:
            status = "selected" if viewer_id and locks[s.id].user_id == viewer_id else "locked"
            locked_by_me = bool(viewer_id and locks[s.id].user_id == viewer_id)
        result.append(
            {
                "id": s.id,
                "label": s.label,
                "row": s.row,
                "column": s.column,
                "status": status,
                "locked_by_me": locked_by_me,
            }
        )
    return result


def lock_seat(db: Session, trip_id: int, seat_id: int, user_id: int) -> SeatLock:
    settings = get_settings()
    purge_expired_locks(db, trip_id)
    trip = db.get(Trip, trip_id)
    if not trip or not trip.active:
        raise HTTPException(404, "Trip not found")
    seat = db.get(Seat, seat_id)
    if not seat or seat.bus_id != trip.bus_id:
        raise HTTPException(400, "Invalid seat for trip")
    if seat.status == "maintenance":
        raise HTTPException(409, "Seat unavailable")

    existing_booking = (
        db.query(Booking)
        .filter(
            Booking.trip_id == trip_id,
            Booking.seat_id == seat_id,
            Booking.status.in_(["pending", "paid", "completed"]),
        )
        .first()
    )
    if existing_booking:
        raise HTTPException(409, "Seat already booked")

    lock = db.query(SeatLock).filter(SeatLock.trip_id == trip_id, SeatLock.seat_id == seat_id).first()
    if lock and lock.user_id != user_id and lock.expires_at > datetime.utcnow():
        raise HTTPException(409, "Seat locked by another passenger")

    # Release other locks held by this user on same trip
    for other in db.query(SeatLock).filter(SeatLock.trip_id == trip_id, SeatLock.user_id == user_id).all():
        if other.seat_id != seat_id:
            db.delete(other)

    expires = datetime.utcnow() + timedelta(seconds=settings.seat_lock_seconds)
    if lock and lock.user_id == user_id:
        lock.expires_at = expires
    else:
        if lock:
            db.delete(lock)
            db.flush()
        lock = SeatLock(trip_id=trip_id, seat_id=seat_id, user_id=user_id, expires_at=expires)
        db.add(lock)
    audit(
        db,
        "seat.locked",
        actor_id=user_id,
        entity_type="seat",
        entity_id=str(seat_id),
        metadata={"trip_id": trip_id},
    )
    db.flush()
    return lock


def release_seat(db: Session, trip_id: int, seat_id: int, user_id: int) -> bool:
    lock = db.query(SeatLock).filter(
        SeatLock.trip_id == trip_id, SeatLock.seat_id == seat_id, SeatLock.user_id == user_id
    ).first()
    if not lock:
        return False
    db.delete(lock)
    audit(db, "seat.released", actor_id=user_id, entity_type="seat", entity_id=str(seat_id))
    db.flush()
    return True


def calculate_totals(
    fare: int,
    *,
    insurance: bool = False,
    luggage: bool = False,
) -> dict:
    settings = get_settings()
    insurance_ugx = settings.insurance_fee_ugx if insurance else 0
    luggage_ugx = settings.luggage_fee_ugx if luggage else 0
    booking_fee = settings.booking_fee_ugx
    total = fare + insurance_ugx + luggage_ugx + booking_fee
    return {
        "fare_ugx": fare,
        "insurance_ugx": insurance_ugx,
        "luggage_ugx": luggage_ugx,
        "booking_fee_ugx": booking_fee,
        "total_ugx": total,
    }


def create_booking(
    db: Session,
    *,
    user_id: int,
    trip_id: int,
    seat_id: int,
    passenger_name: str,
    passenger_phone: str,
    passenger_email: Optional[str],
    special_request: Optional[str],
    include_insurance: bool,
    include_luggage: bool,
    idempotency_key: str,
    client_operation_id: Optional[str] = None,
) -> Booking:
    # Idempotency
    existing = db.query(Booking).filter(Booking.idempotency_key == idempotency_key).first()
    if existing:
        if existing.user_id != user_id:
            raise HTTPException(409, "Idempotency key already belongs to another account")
        return existing
    if client_operation_id:
        by_client = db.query(Booking).filter(Booking.client_operation_id == client_operation_id).first()
        if by_client:
            if by_client.user_id != user_id:
                raise HTTPException(409, "Client operation already belongs to another account")
            return by_client

    purge_expired_locks(db, trip_id)
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    lock = db.query(SeatLock).filter(
        SeatLock.trip_id == trip_id, SeatLock.seat_id == seat_id, SeatLock.user_id == user_id
    ).first()
    if not lock or lock.expires_at < datetime.utcnow():
        raise HTTPException(409, "Seat lock expired — please reselect")

    conflict = (
        db.query(Booking)
        .filter(
            Booking.trip_id == trip_id,
            Booking.seat_id == seat_id,
            Booking.status.in_(["pending", "paid", "completed"]),
        )
        .first()
    )
    if conflict:
        raise HTTPException(409, "Seat already booked")

    totals = calculate_totals(trip.fare_ugx, insurance=include_insurance, luggage=include_luggage)
    booking = Booking(
        user_id=user_id,
        trip_id=trip_id,
        seat_id=seat_id,
        status="pending",
        passenger_name=passenger_name.strip()[:120],
        passenger_phone=passenger_phone.strip()[:32],
        passenger_email=(passenger_email or None),
        special_request=(special_request or None),
        include_insurance=include_insurance,
        include_luggage=include_luggage,
        idempotency_key=idempotency_key,
        client_operation_id=client_operation_id,
        **totals,
    )
    db.add(booking)
    # Consume lock — seat now held by pending booking
    db.delete(lock)
    db.flush()
    audit(
        db,
        "booking.created",
        actor_id=user_id,
        entity_type="booking",
        entity_id=str(booking.id),
        metadata={"trip_id": trip_id, "seat_id": seat_id},
    )
    return booking
