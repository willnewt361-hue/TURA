"""Authentication endpoints."""

from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import COOKIE_NAME, create_access_token, get_current_user
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.security.signing import create_csrf_token, hash_password, verify_password
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

PHONE_RE = re.compile(r"^\+?\d{9,15}$")


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
    role: Literal["customer", "operator", "driver", "admin"] = "customer"


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
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == body.phone.strip()).first()
    if not user or user.status != "active" or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid phone or password")
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
