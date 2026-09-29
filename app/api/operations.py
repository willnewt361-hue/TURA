"""Operator fleet, route, schedule, and live-operations endpoints."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_roles
from app.db.models import Bus, Route, SOSAlert, Seat, Trip, User
from app.db.seed import seat_layout
from app.db.session import get_db
from app.realtime import events
from app.realtime.manager import manager, ops_room
from app.security.signing import hash_password
from app.services.audit import audit
from app.services.tracking_service import latest_position, replay_points

router = APIRouter(prefix="/api/operations", tags=["operations"])
SAFE_SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
SAFE_LABEL = re.compile(r"^[A-Za-z0-9 .'-]{1,80}$")


class BusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate: str = Field(min_length=3, max_length=32)
    operator: str = Field(min_length=2, max_length=80)
    capacity: int = Field(ge=4, le=80)
    amenities: list[str] = Field(default_factory=list, max_length=12)
    rating: float = Field(default=4.5, ge=1, le=5)


class RouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=2, max_length=80)
    destination: str = Field(min_length=2, max_length=80)
    stops: list[str] = Field(default_factory=list, max_length=20)
    distance_km: float = Field(gt=0, le=3000)
    base_fare_ugx: int = Field(gt=0, le=10000000)
    duration_minutes: int = Field(gt=0, le=2880)
    image_slug: str = Field(default="default", min_length=1, max_length=40)


class TripIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bus_id: int = Field(gt=0)
    route_id: int = Field(gt=0)
    departure: datetime
    arrival: datetime
    driver_id: Optional[int] = Field(default=None, gt=0)
    fare_ugx: Optional[int] = Field(default=None, gt=0, le=10000000)


class StaffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=32)
    password: str = Field(min_length=12, max_length=72)
    role: Literal["driver", "operator"]


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _trip_out(db: Session, trip: Trip) -> dict:
    position = latest_position(db, trip.id)
    return {
        "id": trip.id,
        "bus_id": trip.bus_id,
        "route_id": trip.route_id,
        "driver_id": trip.driver_id,
        "departure": trip.departure.isoformat(),
        "arrival": trip.arrival.isoformat(),
        "status": trip.status,
        "active": trip.active,
        "fare_ugx": trip.fare_ugx,
        "origin": trip.route.origin,
        "destination": trip.route.destination,
        "operator": trip.bus.operator,
        "plate": trip.bus.plate,
        "position": position,
    }


@router.get("/setup")
def setup(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    buses = db.query(Bus).order_by(Bus.operator, Bus.plate).all()
    routes = db.query(Route).order_by(Route.origin, Route.destination).all()
    drivers = (
        db.query(User)
        .filter(User.role == "driver", User.status == "active")
        .order_by(User.name)
        .all()
    )
    return {
        "buses": [
            {
                "id": bus.id,
                "plate": bus.plate,
                "operator": bus.operator,
                "capacity": bus.capacity,
                "amenities": [value for value in bus.amenities.split(",") if value],
                "rating": bus.rating,
            }
            for bus in buses
        ],
        "routes": [
            {
                "id": route.id,
                "origin": route.origin,
                "destination": route.destination,
                "stops": [value for value in route.stops.split(",") if value],
                "distance_km": route.distance_km,
                "base_fare_ugx": route.base_fare_ugx,
                "duration_minutes": route.duration_minutes,
                "image_slug": route.image_slug,
            }
            for route in routes
        ],
        "drivers": [{"id": driver.id, "name": driver.name} for driver in drivers],
    }


@router.get("/my-trips")
def my_trips(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("driver", "operator", "admin")),
):
    query = (
        db.query(Trip)
        .options(joinedload(Trip.route), joinedload(Trip.bus))
        .filter(
            Trip.active.is_(True),
            Trip.status.in_(["scheduled", "boarding", "en_route"]),
        )
    )
    if user.role == "driver":
        query = query.filter(Trip.driver_id == user.id)
    trips = query.order_by(Trip.departure).limit(100).all()
    return {"trips": [_trip_out(db, trip) for trip in trips]}


@router.post("/staff", status_code=201)
async def create_staff(
    body: StaffIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    phone = body.phone.strip()
    name = body.name.strip()
    if not re.fullmatch(r"\+?\d{9,15}", phone):
        raise HTTPException(400, "Invalid staff phone number")
    if len(name) < 2:
        raise HTTPException(400, "Staff name must contain at least two characters")
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(409, "Phone already registered")
    staff = User(
        role=body.role,
        name=name,
        phone=phone,
        password_hash=hash_password(body.password),
        language="en",
        status="active",
    )
    db.add(staff)
    try:
        db.flush()
        audit(db, "staff.created", actor_id=user.id, entity_type="user", entity_id=str(staff.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Phone already registered") from exc
    await manager.broadcast(ops_room(), events.OPERATIONS_UPDATED, {"kind": "staff"})
    return {"id": staff.id, "name": staff.name, "phone": staff.phone, "role": staff.role}


@router.post("/buses", status_code=201)
async def create_bus(
    body: BusIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    plate = body.plate.strip().upper()
    operator = body.operator.strip()
    amenities = [value.strip().lower() for value in body.amenities]
    if not SAFE_LABEL.fullmatch(operator) or not SAFE_LABEL.fullmatch(plate):
        raise HTTPException(400, "Bus operator and plate must use plain text")
    if any(not SAFE_SLUG.fullmatch(value) for value in amenities):
        raise HTTPException(400, "Amenities may contain only lowercase letters, numbers, and hyphens")
    if db.query(Bus).filter(Bus.plate == plate).first():
        raise HTTPException(409, "Bus plate already exists")

    bus = Bus(
        plate=plate,
        operator=operator,
        capacity=body.capacity,
        amenities=",".join(dict.fromkeys(amenities)),
        rating=body.rating,
        status="active",
    )
    db.add(bus)
    try:
        db.flush()
        for label, row, column in seat_layout(bus.capacity):
            db.add(Seat(bus_id=bus.id, label=label, row=row, column=column, status="available"))
        audit(db, "fleet.bus_created", actor_id=user.id, entity_type="bus", entity_id=str(bus.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Bus plate already exists") from exc
    await manager.broadcast(ops_room(), events.OPERATIONS_UPDATED, {"kind": "bus"})
    return {"id": bus.id, "plate": bus.plate, "operator": bus.operator, "capacity": bus.capacity}


@router.post("/routes", status_code=201)
async def create_route(
    body: RouteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    origin = body.origin.strip()
    destination = body.destination.strip()
    stops = [stop.strip() for stop in body.stops]
    if origin.casefold() == destination.casefold():
        raise HTTPException(400, "Route origin and destination must differ")
    if not all(SAFE_LABEL.fullmatch(place) for place in [origin, destination, *stops]):
        raise HTTPException(400, "Route locations must use plain text")
    if not SAFE_SLUG.fullmatch(body.image_slug):
        raise HTTPException(400, "Invalid route image category")
    if (
        db.query(Route)
        .filter(Route.origin.ilike(origin), Route.destination.ilike(destination))
        .first()
    ):
        raise HTTPException(409, "Route already exists")

    route = Route(
        origin=origin,
        destination=destination,
        stops=",".join(stops),
        distance_km=body.distance_km,
        base_fare_ugx=body.base_fare_ugx,
        duration_minutes=body.duration_minutes,
        image_slug=body.image_slug,
    )
    db.add(route)
    db.flush()
    audit(db, "route.created", actor_id=user.id, entity_type="route", entity_id=str(route.id))
    db.commit()
    await manager.broadcast(ops_room(), events.OPERATIONS_UPDATED, {"kind": "route"})
    return {"id": route.id, "origin": route.origin, "destination": route.destination}


@router.post("/trips", status_code=201)
async def create_trip(
    body: TripIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    departure = _as_utc_naive(body.departure)
    arrival = _as_utc_naive(body.arrival)
    if departure <= datetime.utcnow():
        raise HTTPException(400, "Trip departure must be in the future (UTC)")
    if arrival <= departure:
        raise HTTPException(400, "Trip arrival must be after departure")
    bus = db.get(Bus, body.bus_id)
    route = db.get(Route, body.route_id)
    if not bus or bus.status != "active":
        raise HTTPException(404, "Active bus not found")
    if not route:
        raise HTTPException(404, "Route not found")
    driver = None
    if body.driver_id is not None:
        driver = db.get(User, body.driver_id)
        if not driver or driver.role != "driver" or driver.status != "active":
            raise HTTPException(400, "An active driver account is required")

    bus_overlap = (
        db.query(Trip)
        .filter(
            Trip.bus_id == bus.id,
            Trip.active.is_(True),
            Trip.status != "cancelled",
            Trip.departure < arrival,
            Trip.arrival > departure,
        )
        .first()
    )
    if bus_overlap:
        raise HTTPException(409, "Bus is already scheduled for an overlapping trip")
    if driver:
        driver_overlap = (
            db.query(Trip)
            .filter(
                Trip.driver_id == driver.id,
                Trip.active.is_(True),
                Trip.status != "cancelled",
                Trip.departure < arrival,
                Trip.arrival > departure,
            )
            .first()
        )
        if driver_overlap:
            raise HTTPException(409, "Driver is already assigned to an overlapping trip")

    trip = Trip(
        bus_id=bus.id,
        route_id=route.id,
        departure=departure,
        arrival=arrival,
        driver_id=driver.id if driver else None,
        fare_ugx=body.fare_ugx or route.base_fare_ugx,
        status="scheduled",
        active=True,
    )
    db.add(trip)
    db.flush()
    audit(db, "trip.created", actor_id=user.id, entity_type="trip", entity_id=str(trip.id))
    db.commit()
    result = {"trip": _trip_out(db, trip)}
    await manager.broadcast(ops_room(), events.OPERATIONS_UPDATED, {"kind": "trip"})
    return result


@router.get("/trips")
def list_trips(
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.route), joinedload(Trip.bus))
        .order_by(Trip.departure.desc())
        .limit(limit)
        .all()
    )
    return {"trips": [_trip_out(db, trip) for trip in trips]}


@router.get("/trips/{trip_id}/replay")
def trip_replay(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.route), joinedload(Trip.bus))
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(404, "Trip not found")
    return {"trip": _trip_out(db, trip), "points": replay_points(db, trip_id)}


@router.get("/incidents")
def incidents(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    alerts = (
        db.query(SOSAlert)
        .order_by(SOSAlert.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "incidents": [
            {
                "id": alert.id,
                "trip_id": alert.trip_id,
                "reason": alert.reason,
                "location": alert.location,
                "status": alert.status,
                "demo_note": alert.demo_note,
                "created_at": alert.created_at.isoformat(),
                "acknowledged_at": alert.acknowledged_at.isoformat()
                if alert.acknowledged_at
                else None,
            }
            for alert in alerts
        ]
    }


@router.get("/live")
def live_operations(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("operator", "admin")),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.route), joinedload(Trip.bus))
        .filter(
            Trip.active.is_(True),
            Trip.status.in_(["scheduled", "boarding", "en_route"]),
        )
        .order_by(Trip.departure)
        .limit(100)
        .all()
    )
    incidents_response = incidents(db, user)
    return {
        "trips": [_trip_out(db, trip) for trip in trips],
        "incidents": incidents_response["incidents"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
