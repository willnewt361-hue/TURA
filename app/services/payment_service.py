"""Payment provider interface + mock provider."""

from __future__ import annotations

import abc
import secrets
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Booking, Payment
from app.services.audit import audit


@dataclass
class PaymentResult:
    success: bool
    provider_ref: Optional[str]
    status: str
    message: str


class PaymentProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def charge(
        self,
        amount: int,
        method: str,
        metadata: dict,
    ) -> PaymentResult:
        raise NotImplementedError


class MockPaymentProvider(PaymentProvider):
    """Local mock — no real MoMo/card calls. Integration boundary for MTN/Airtel later."""

    name = "mock"

    def charge(self, amount: int, method: str, metadata: dict) -> PaymentResult:
        # Simulate failure when phone ends with 0000 (demo failure path)
        phone = str(metadata.get("phone", ""))
        if phone.endswith("0000"):
            return PaymentResult(False, None, "failed", "Mock payment declined (demo failure)")
        ref = f"MOCK-{secrets.token_hex(6).upper()}"
        return PaymentResult(True, ref, "success", "Mock payment accepted")


def get_payment_provider() -> PaymentProvider:
    return MockPaymentProvider()


def process_payment(
    db: Session,
    booking: Booking,
    *,
    method: str,
    idempotency_key: str,
    actor_id: int,
) -> Payment:
    existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
    if existing:
        if existing.booking_id != booking.id:
            raise HTTPException(409, "Payment idempotency key already belongs to another booking")
        return existing

    # Also idempotent on booking already paid
    if booking.payment and booking.payment.status == "success":
        return booking.payment
    if booking.status != "pending":
        raise HTTPException(409, "Booking is not awaiting payment")

    provider = get_payment_provider()
    result = provider.charge(
        booking.total_ugx,
        method,
        {"booking_id": booking.id, "phone": booking.passenger_phone},
    )
    payment = Payment(
        booking_id=booking.id,
        provider=provider.name,
        method=method,
        amount=booking.total_ugx,
        status=result.status,
        provider_ref=result.provider_ref,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    db.flush()
    if result.success:
        booking.status = "paid"
    else:
        booking.status = "cancelled"
    audit(
        db,
        "payment.processed",
        actor_id=actor_id,
        entity_type="payment",
        entity_id=str(payment.id),
        metadata={"status": result.status, "method": method, "provider": provider.name},
    )
    return payment


def new_idempotency_key() -> str:
    return uuid.uuid4().hex
