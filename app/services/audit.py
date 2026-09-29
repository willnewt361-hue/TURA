"""Audit event helper."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def audit(
    db: Session,
    event_type: str,
    *,
    actor_id: Optional[int] = None,
    entity_type: str = "",
    entity_id: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> AuditEvent:
    evt = AuditEvent(
        actor_id=actor_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(evt)
    db.flush()
    return evt
