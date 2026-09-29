"""Auth dependencies — cookie sessions with signed JWT."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Trip, User
from app.db.session import get_db

ALGORITHM = "HS256"
COOKIE_NAME = "tura_session"


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=12),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired session") from exc


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Authentication required")
    data = decode_token(token)
    user = db.get(User, int(data["sub"]))
    if not user or user.status != "active":
        raise HTTPException(401, "User inactive or not found")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        data = decode_token(token)
        return db.get(User, int(data["sub"]))
    except HTTPException:
        return None


def require_roles(*roles: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != "admin":
            raise HTTPException(403, "Insufficient permissions")
        return user

    return _dep


def require_trip_assignment(db: Session, trip_id: int, user: User) -> Trip:
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    if user.role in ("admin", "operator"):
        return trip
    if user.role == "driver" and trip.driver_id == user.id:
        return trip
    raise HTTPException(403, "You are not assigned to this trip")
