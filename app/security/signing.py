"""Ticket signing, password hashing, CSRF helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

import bcrypt

from app.config import get_settings


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("ascii"))
    except (TypeError, ValueError):
        return False


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def sign_ticket_payload(payload: dict[str, Any]) -> str:
    """Create compact tamper-evident ticket token (HMAC). Never embed secrets."""
    settings = get_settings()
    body = {
        "ticket_id": payload["ticket_id"],
        "ticket_no": payload["ticket_no"],
        "trip_id": payload["trip_id"],
        "seat_id": payload["seat_id"],
        "issued_at": payload["issued_at"],
        "expires_at": payload["expires_at"],
        "version": payload.get("version", 1),
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(
        settings.ticket_hmac_secret.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token_obj = {"d": body, "s": sig}
    encoded = base64.urlsafe_b64encode(
        json.dumps(token_obj, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    return encoded


def verify_ticket_token(token: str) -> tuple[bool, Optional[dict], str]:
    """Verify HMAC signature and expiry. Returns (ok, payload, reason)."""
    settings = get_settings()
    try:
        pad = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(token + pad)
        token_obj = json.loads(decoded.decode("utf-8"))
        body = token_obj.get("d")
        sig = token_obj.get("s")
        if not body or not sig:
            return False, None, "Malformed token"
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True)
        expected = hmac.new(
            settings.ticket_hmac_secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False, None, "Invalid signature"
        expires = datetime.fromisoformat(body["expires_at"])
        if datetime.utcnow() > expires:
            return False, body, "Ticket expired"
        return True, body, "ok"
    except Exception:
        return False, None, "Invalid token"


def make_ticket_no(seq: int) -> str:
    stamp = datetime.utcnow().strftime("%y%m%d")
    return f"TURA{stamp}{seq:04d}"


def default_ticket_expiry() -> datetime:
    settings = get_settings()
    return datetime.utcnow() + timedelta(hours=settings.ticket_validity_hours)
