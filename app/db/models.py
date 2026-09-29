"""SQLAlchemy models for TURA."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(32), index=True)  # customer|operator|driver|admin
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(8), default="en")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")


class Bus(Base):
    __tablename__ = "buses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), unique=True)
    operator: Mapped[str] = mapped_column(String(80))
    capacity: Mapped[int] = mapped_column(Integer, default=40)
    amenities: Mapped[str] = mapped_column(String(255), default="wifi,ac,power")  # csv
    rating: Mapped[float] = mapped_column(Float, default=4.5)
    status: Mapped[str] = mapped_column(String(20), default="active")

    seats: Mapped[list["Seat"]] = relationship(back_populates="bus")
    trips: Mapped[list["Trip"]] = relationship(back_populates="bus")


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(80), index=True)
    destination: Mapped[str] = mapped_column(String(80), index=True)
    stops: Mapped[str] = mapped_column(Text, default="")  # csv
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    base_fare_ugx: Mapped[int] = mapped_column(Integer, default=40000)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=360)
    image_slug: Mapped[str] = mapped_column(String(40), default="default")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id"))
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    departure: Mapped[datetime] = mapped_column(DateTime, index=True)
    arrival: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|boarding|en_route|arrived|cancelled
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    fare_ugx: Mapped[int] = mapped_column(Integer, default=40000)
    driver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    bus: Mapped["Bus"] = relationship(back_populates="trips")
    route: Mapped["Route"] = relationship()
    bookings: Mapped[list["Booking"]] = relationship(back_populates="trip")
    tracking_points: Mapped[list["TrackingPoint"]] = relationship(back_populates="trip")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("bus_id", "label", name="uq_bus_seat_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id"), index=True)
    label: Mapped[str] = mapped_column(String(8))
    row: Mapped[int] = mapped_column(Integer)
    column: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|maintenance

    bus: Mapped["Bus"] = relationship(back_populates="seats")


class SeatLock(Base):
    """Server-authoritative short-lived seat reservation."""

    __tablename__ = "seat_locks"
    __table_args__ = (
        UniqueConstraint("trip_id", "seat_id", name="uq_trip_seat_lock"),
        Index("ix_seat_lock_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_booking_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|paid|cancelled|completed
    passenger_name: Mapped[str] = mapped_column(String(120))
    passenger_phone: Mapped[str] = mapped_column(String(32))
    passenger_email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    special_request: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fare_ugx: Mapped[int] = mapped_column(Integer)
    insurance_ugx: Mapped[int] = mapped_column(Integer, default=0)
    luggage_ugx: Mapped[int] = mapped_column(Integer, default=0)
    booking_fee_ugx: Mapped[int] = mapped_column(Integer, default=0)
    total_ugx: Mapped[int] = mapped_column(Integer)
    include_insurance: Mapped[bool] = mapped_column(Boolean, default=False)
    include_luggage: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    client_operation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="bookings")
    trip: Mapped["Trip"] = relationship(back_populates="bookings")
    seat: Mapped["Seat"] = relationship()
    payment: Mapped[Optional["Payment"]] = relationship(back_populates="booking", uselist=False)
    ticket: Mapped[Optional["Ticket"]] = relationship(back_populates="booking", uselist=False)
    luggage: Mapped[Optional["Luggage"]] = relationship(back_populates="booking", uselist=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_payment_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    method: Mapped[str] = mapped_column(String(40), default="mobile_money")  # mobile_money|card|bank
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|success|failed
    provider_ref: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    booking: Mapped["Booking"] = relationship(back_populates="payment")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)
    signed_payload: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="valid")  # valid|used|cancelled|expired
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    validated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="ticket")


class Luggage(Base):
    __tablename__ = "luggage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)
    tag_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    fee: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="registered")  # registered|loaded|received|claimed|lost
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    booking: Mapped["Booking"] = relationship(back_populates="luggage")


class TrackingPoint(Base):
    __tablename__ = "tracking_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(80), default="")
    progress_pct: Mapped[float] = mapped_column(Float, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trip: Mapped["Trip"] = relationship(back_populates="tracking_points")


class SOSAlert(Base):
    __tablename__ = "sos_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    trip_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trips.id"), nullable=True)
    sos_type: Mapped[str] = mapped_column(String(40), default="private_operational")
    reason: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|acknowledged|resolved
    demo_note: Mapped[str] = mapped_column(String(80), default="Demo/Local alert")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), unique=True)
    gross: Mapped[int] = mapped_column(Integer, default=0)
    fees: Mapped[int] = mapped_column(Integer, default=0)
    net: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
