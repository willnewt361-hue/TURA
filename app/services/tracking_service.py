"""Trip tracking simulator and replay."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import TrackingPoint, Trip
from app.services.audit import audit

# Approximate Uganda corridor waypoints for demo routes
ROUTE_WAYPOINTS = {
    ("Kampala", "Gulu"): [
        (0.3476, 32.5825, "Kampala"),
        (0.6167, 32.3000, "Near Luwero"),
        (1.4333, 32.0500, "Near Masindi"),
        (2.2950, 32.3000, "Near Karuma"),
        (2.7746, 32.2990, "Gulu"),
    ],
    ("Kampala", "Mbarara"): [
        (0.3476, 32.5825, "Kampala"),
        (0.1833, 31.7667, "Near Masaka"),
        (-0.4167, 31.0500, "Near Lyantonde"),
        (-0.6072, 30.6545, "Mbarara"),
    ],
    ("Kampala", "Mbale"): [
        (0.3476, 32.5825, "Kampala"),
        (0.4500, 33.2000, "Near Jinja"),
        (0.9500, 33.8000, "Near Tororo"),
        (1.0820, 34.1750, "Mbale"),
    ],
    ("Kampala", "Jinja"): [
        (0.3476, 32.5825, "Kampala"),
        (0.4000, 32.9000, "Near Mukono"),
        (0.4244, 33.2041, "Jinja"),
    ],
}


def waypoints_for_trip(trip: Trip) -> list[tuple]:
    key = (trip.route.origin, trip.route.destination)
    return ROUTE_WAYPOINTS.get(key) or ROUTE_WAYPOINTS[("Kampala", "Gulu")]


def advance_tracking(db: Session, trip_id: int, actor_id: Optional[int] = None) -> TrackingPoint:
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    points = waypoints_for_trip(trip)
    existing = (
        db.query(TrackingPoint)
        .filter(TrackingPoint.trip_id == trip_id)
        .order_by(TrackingPoint.id)
        .all()
    )
    idx = min(len(existing), len(points) - 1)
    if len(existing) >= len(points):
        idx = len(points) - 1
        lat, lng, label = points[idx]
        progress = 100.0
        trip.status = "arrived"
    else:
        lat, lng, label = points[idx]
        progress = round(100.0 * idx / (len(points) - 1), 1)
        if idx == 0:
            trip.status = "boarding"
        elif idx < len(points) - 1:
            trip.status = "en_route"
        else:
            trip.status = "arrived"

    point = TrackingPoint(
        trip_id=trip_id,
        lat=lat,
        lng=lng,
        label=label,
        progress_pct=progress,
        timestamp=datetime.utcnow(),
    )
    db.add(point)
    audit(
        db,
        "trip.position",
        actor_id=actor_id,
        entity_type="trip",
        entity_id=str(trip_id),
        metadata={"label": label, "progress": progress},
    )
    db.flush()
    return point


def latest_position(db: Session, trip_id: int) -> Optional[dict]:
    point = (
        db.query(TrackingPoint)
        .filter(TrackingPoint.trip_id == trip_id)
        .order_by(TrackingPoint.id.desc())
        .first()
    )
    if not point:
        return None
    return {
        "lat": point.lat,
        "lng": point.lng,
        "label": point.label,
        "progress_pct": point.progress_pct,
        "timestamp": point.timestamp.isoformat(),
    }


def replay_points(db: Session, trip_id: int) -> list[dict]:
    points = (
        db.query(TrackingPoint)
        .filter(TrackingPoint.trip_id == trip_id)
        .order_by(TrackingPoint.id)
        .all()
    )
    return [
        {
            "lat": p.lat,
            "lng": p.lng,
            "label": p.label,
            "progress_pct": p.progress_pct,
            "timestamp": p.timestamp.isoformat(),
        }
        for p in points
    ]
