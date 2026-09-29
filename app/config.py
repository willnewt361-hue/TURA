"""Application configuration — fees, flags, secrets from env."""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tura_env: str = "development"
    secret_key: str = ""
    ticket_hmac_secret: str = ""
    database_url: str = "sqlite:///./data/tura.db"
    cors_origins: str = ""
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    rate_limit_per_minute: int = 60
    seat_lock_seconds: int = 120
    ticket_validity_hours: int = 72
    demo_mode: bool = True
    demo_instance: bool = False
    feature_sos: bool = True
    feature_luggage: bool = True
    feature_trip_replay: bool = True
    feature_i18n: bool = True
    default_language: str = "en"
    host: str = "127.0.0.1"
    port: int = 8000

    # Configurable fee engine (UGX)
    base_fare_ugx: int = 40000
    luggage_fee_ugx: int = 5000
    insurance_fee_ugx: int = 2000
    booking_fee_ugx: int = 500
    commission_pct: float = 5.0
    currency: str = "UGX"

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        if not self.is_production:
            self.secret_key = self.secret_key or secrets.token_hex(32)
            self.ticket_hmac_secret = self.ticket_hmac_secret or secrets.token_hex(32)
            return self

        placeholders = {"change-me", "changeme", "secret", "password"}
        for name in ("secret_key", "ticket_hmac_secret"):
            value = getattr(self, name).strip()
            if (
                len(value) < 32
                or len(set(value)) < 12
                or value.lower() in placeholders
                or "change-me" in value.lower()
            ):
                raise ValueError(f"{name.upper()} must be a unique secret of at least 32 characters in production")

        if secrets.compare_digest(self.secret_key, self.ticket_hmac_secret):
            raise ValueError("SECRET_KEY and TICKET_HMAC_SECRET must be different in production")
        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if self.demo_mode != self.demo_instance:
            raise ValueError("In production, DEMO_MODE must match the explicitly isolated DEMO_INSTANCE setting")
        if "*" in self.cors_origin_list:
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if self.session_cookie_samesite.lower() not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
        if self.session_cookie_samesite.lower() == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None cookies require SESSION_COOKIE_SECURE=true")
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.tura_env.lower() == "production"

    def fee_config(self) -> dict:
        return {
            "currency": self.currency,
            "base_fare_ugx": self.base_fare_ugx,
            "luggage_fee_ugx": self.luggage_fee_ugx,
            "insurance_fee_ugx": self.insurance_fee_ugx,
            "booking_fee_ugx": self.booking_fee_ugx,
            "commission_pct": self.commission_pct,
            "seat_lock_seconds": self.seat_lock_seconds,
            "ticket_validity_hours": self.ticket_validity_hours,
        }

    def feature_flags(self) -> dict:
        return {
            "sos": self.feature_sos,
            "luggage": self.feature_luggage,
            "trip_replay": self.feature_trip_replay,
            "i18n": self.feature_i18n,
            "demo_mode": self.demo_mode,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
