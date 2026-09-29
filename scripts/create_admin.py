"""Create the first administrator for a non-demo deployment."""

from __future__ import annotations

import getpass
import re

from app.db.models import User
from app.db.session import SessionLocal, init_db
from app.security.signing import hash_password
from app.services.audit import audit

PHONE_RE = re.compile(r"^\+?\d{9,15}$")


def main() -> None:
    init_db()
    name = input("Administrator name: ").strip()
    phone = input("Administrator phone: ").strip()
    password = getpass.getpass("Administrator password (12-72 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(name) < 2:
        raise SystemExit("Name must contain at least two characters.")
    if not PHONE_RE.fullmatch(phone):
        raise SystemExit("Phone must contain 9-15 digits and may start with +.")
    if not 12 <= len(password) <= 72:
        raise SystemExit("Password must contain between 12 and 72 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == "admin").first():
            raise SystemExit("An administrator already exists.")
        if db.query(User).filter(User.phone == phone).first():
            raise SystemExit("That phone is already registered.")
        admin = User(
            role="admin",
            name=name[:120],
            phone=phone,
            password_hash=hash_password(password),
            language="en",
            status="active",
        )
        db.add(admin)
        db.flush()
        audit(
            db,
            "admin.bootstrap",
            actor_id=admin.id,
            entity_type="user",
            entity_id=str(admin.id),
        )
        db.commit()
        print("Administrator created. Remove any temporary bootstrap access and keep credentials private.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
