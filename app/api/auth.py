"""Authentication endpoints."""

from __future__ import annotations

import re
import threading
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import COOKIE_NAME, create_access_token, get_current_user, require_roles
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.security.signing import create_csrf_token, hash_password, verify_password
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

PHONE_RE = re.compile(r"^\+?\d{9,15}$")

# Constant-time decoy hash so unknown-phone logins cost the same as real ones.
_DUMMY_HASH = hash_password("tura-login-timing-decoy")
_failure_lock = threading.Lock()
_login_failures: dict[str, list[float]] = {}


def _client_key(request: Request, phone: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{phone}|{host}"


def _check_login_lock(key: str, phone: str) -> None:
    settings = get_settings()
    now = time.time()
    window = settings.login_lockout_seconds
    with _failure_lock:
        for bucket, limit in (
            (key, settings.login_max_failures),
            (phone, settings.login_max_failures * 4),
        ):
            attempts = [t for t in _login_failures.get(bucket, []) if now - t < window]
            if attempts:
                _login_failures[bucket] = attempts
            else:
                _login_failures.pop(bucket, None)
            if len(attempts) >= limit:
                raise HTTPException(429, "Too many failed attempts. Try again later.")


def _record_login_failure(key: str, phone: str) -> None:
    settings = get_settings()
    now = time.time()
    window = settings.login_lockout_seconds
    with _failure_lock:
        _login_failures.setdefault(key, []).append(now)
        # Phone-wide bucket is looser than the per-IP bucket.
        phone_bucket = _login_failures.setdefault(phone, [])
        phone_bucket.append(now)
        phone_bucket[:] = [t for t in phone_bucket if now - t < window]
        _login_failures[key] = [t for t in _login_failures[key] if now - t < window]


def _clear_login_failures(key: str, phone: str) -> None:
    with _failure_lock:
        _login_failures.pop(key, None)
        _login_failures.pop(phone, None)


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=32)
    password: str = Field(min_length=8, max_length=72)
    email: Optional[str] = Field(default=None, max_length=160)
    language: str = Field(default="en", max_length=8)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=9, max_length=32)
    password: str = Field(min_length=1, max_length=72)


class DemoLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["customer", "operator", "driver", "admin"] = "customer"


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class ResetPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=9, max_length=32)
    new_password: str = Field(min_length=8, max_length=72)


def _set_session(response: Response, user: User) -> str:
    settings = get_settings()
    token = create_access_token(user.id, user.role)
    csrf = create_csrf_token()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=12 * 3600,
        path="/",
    )
    response.set_cookie(
        "tura_csrf",
        csrf,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=12 * 3600,
        path="/",
    )
    return csrf


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "role": user.role,
        "language": user.language,
    }


@router.post("/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(400, "Invalid phone number")
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(400, "Name must contain at least two non-space characters")
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(400, "Phone already registered")
    user = User(
        role="customer",
        name=name[:120],
        phone=phone,
        email=(body.email.strip()[:160] if body.email else None),
        password_hash=hash_password(body.password),
        language=body.language if body.language in ("en", "lg") else "en",
        status="active",
    )
    db.add(user)
    try:
        db.flush()
        audit(db, "auth.register", actor_id=user.id, entity_type="user", entity_id=str(user.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Phone already registered") from exc
    csrf = _set_session(response, user)
    return {"user": _user_out(user), "csrf": csrf}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    key = _client_key(request, phone)
    _check_login_lock(key, phone)

    user = db.query(User).filter(User.phone == phone).first()
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or user.status != "active" or not password_ok:
        _record_login_failure(key, phone)
        raise HTTPException(401, "Invalid phone or password")

    _clear_login_failures(key, phone)
    audit(db, "auth.login", actor_id=user.id, entity_type="user", entity_id=str(user.id))
    db.commit()
    csrf = _set_session(response, user)
    return {"user": _user_out(user), "csrf": csrf}


@router.post("/demo-login")
def demo_login(body: DemoLoginIn, response: Response, db: Session = Depends(get_db)):
    if not get_settings().demo_mode:
        raise HTTPException(403, "Demo mode disabled")
    role = body.role
    if role == "customer":
        user = db.query(User).filter(User.phone == "+256700000001").first()
    else:
        user = db.query(User).filter(User.role == role).first()
    if not user or user.status != "active":
        raise HTTPException(404, "Demo user missing — restart server to seed")
    csrf = _set_session(response, user)
    return {"user": _user_out(user), "csrf": csrf, "demo": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie("tura_csrf", path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": _user_out(user)}


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Let a signed-in user rotate their own password."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(400, "New password must be different")
    user.password_hash = hash_password(body.new_password)
    audit(db, "auth.password_changed", actor_id=user.id, entity_type="user", entity_id=str(user.id))
    db.commit()
    return {"ok": True}


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    """Admin-assisted reset for passengers who cannot sign in.

    There is no email/SMS delivery in this build, so a staff member verifies the
    person at the counter and sets a temporary password. The action is audited.
    """
    phone = body.phone.strip()
    target = db.query(User).filter(User.phone == phone).first()
    if not target:
        raise HTTPException(404, "No account with that phone number")
    target.password_hash = hash_password(body.new_password)
    audit(
        db,
        "auth.password_reset",
        actor_id=admin.id,
        entity_type="user",
        entity_id=str(target.id),
    )
    db.commit()
    return {"ok": True, "phone": target.phone}


@router.get("/csrf")
def csrf_token(response: Response):
    settings = get_settings()
    token = create_csrf_token()
    response.set_cookie(
        "tura_csrf",
        token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=12 * 3600,
        path="/",
    )
    return {"csrf": token}
