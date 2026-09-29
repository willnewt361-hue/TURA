"""Seed demo users, fleet, routes, trips and seats."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Bus, Route, Seat, Trip, User
from app.security.signing import hash_password


DEMO_USERS = [
    {"role": "customer", "name": "Mike Okello", "phone": "+256700000001", "email": "mike@tura.demo", "password": "demo1234"},
    {"role": "customer", "name": "Amina Nalubega", "phone": "+256700000002", "email": "amina@tura.demo", "password": "demo1234"},
    {"role": "operator", "name": "Ops Manager", "phone": "+256700000010", "email": "ops@tura.demo", "password": "ops1234"},
    {"role": "driver", "name": "Driver Kato", "phone": "+256700000020", "email": "driver@tura.demo", "password": "driver1234"},
    {"role": "admin", "name": "TURA Admin", "phone": "+256700000099", "email": "admin@tura.demo", "password": "admin1234"},
]

CITIES = [
    ("Kampala", "Gulu", "Luwero,Masindi,Karuma", 340, 40000, 420, "gulu"),
    ("Kampala", "Mbarara", "Masaka,Lyantonde", 270, 35000, 300, "mbarara"),
    ("Kampala", "Mbale", "Jinja,Tororo", 245, 32000, 280, "mbale"),
    ("Kampala", "Jinja", "Mukono", 80, 18000, 90, "jinja"),
    ("Gulu", "Kampala", "Karuma,Masindi,Luwero", 340, 40000, 420, "kampala"),
    ("Mbarara", "Kampala", "Lyantonde,Masaka", 270, 35000, 300, "kampala"),
]

BUSES = [
    ("UBA 123A", "Modern Coast", 40, "wifi,ac,power", 4.7),
    ("UBB 456B", "Gateway Bus", 36, "wifi,ac", 4.5),
    ("UBC 789C", "YY Coaches", 44, "wifi,ac,power,toilet", 4.8),
    ("UBD 321D", "Link Bus", 40, "ac,power", 4.3),
]


def seat_layout(capacity: int) -> list[tuple[str, int, int]]:
    """2x2 aisle layout: columns 0,1 aisle 2,3 → labels like 1A 1B 1C 1D."""
    seats = []
    rows = max(capacity // 4, 8)
    letters = ["A", "B", "C", "D"]
    cols = [0, 1, 3, 4]  # skip aisle column 2
    n = 0
    for r in range(1, rows + 1):
        for i, letter in enumerate(letters):
            if n >= capacity:
                return seats
            seats.append((f"{r}{letter}", r, cols[i]))
            n += 1
    return seats


def seed_if_empty(db: Session) -> None:
    if db.query(User).first():
        return

    settings = get_settings()
    if not settings.demo_mode:
        return

    users = {}
    for u in DEMO_USERS:
        user = User(
            role=u["role"],
            name=u["name"],
            phone=u["phone"],
            email=u["email"],
            password_hash=hash_password(u["password"]),
            language=settings.default_language,
            status="active",
        )
        db.add(user)
        db.flush()
        users[u["role"] if u["role"] != "customer" else u["phone"]] = user

    routes = []
    for origin, dest, stops, dist, fare, mins, slug in CITIES:
        r = Route(
            origin=origin,
            destination=dest,
            stops=stops,
            distance_km=dist,
            base_fare_ugx=fare,
            duration_minutes=mins,
            image_slug=slug,
        )
        db.add(r)
        db.flush()
        routes.append(r)

    buses = []
    for plate, operator, cap, amenities, rating in BUSES:
        bus = Bus(plate=plate, operator=operator, capacity=cap, amenities=amenities, rating=rating)
        db.add(bus)
        db.flush()
        for label, row, col in seat_layout(cap):
            db.add(Seat(bus_id=bus.id, label=label, row=row, column=col, status="available"))
        buses.append(bus)

    driver = users.get("driver")
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    # Create trips for next 7 days across routes
    trip_i = 0
    for day in range(0, 7):
        for ri, route in enumerate(routes):
            bus = buses[trip_i % len(buses)]
            dep_hour = 6 + (ri % 4) * 3
            departure = now + timedelta(days=day, hours=dep_hour - now.hour if day == 0 else 0)
            if day == 0:
                departure = now.replace(hour=dep_hour)
                if departure < now:
                    departure += timedelta(days=1)
            else:
                departure = (now + timedelta(days=day)).replace(hour=dep_hour)
            arrival = departure + timedelta(minutes=route.duration_minutes)
            trip = Trip(
                bus_id=bus.id,
                route_id=route.id,
                departure=departure,
                arrival=arrival,
                status="scheduled",
                active=True,
                fare_ugx=route.base_fare_ugx,
                driver_id=driver.id if driver else None,
            )
            db.add(trip)
            trip_i += 1

    db.commit()
