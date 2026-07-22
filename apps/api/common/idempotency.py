from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any, cast

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.exceptions import DomainAPIException
from common.models import IdempotencyKey


def _json_safe(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(value, cls=DjangoJSONEncoder)))


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        cls=DjangoJSONEncoder,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def begin_idempotency(
    *,
    scope_type: str,
    scope_id: uuid.UUID | str | None,
    key: str,
    payload: object,
    ttl: timedelta = timedelta(hours=24),
) -> tuple[IdempotencyKey, dict[str, Any] | None]:
    fingerprint = _fingerprint(payload)
    record = (
        IdempotencyKey.objects.select_for_update().filter(scope_type=scope_type, scope_id=scope_id, key=key).first()
    )
    if record is None:
        try:
            with transaction.atomic():
                record = IdempotencyKey.objects.create(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    key=key,
                    request_hash=fingerprint,
                    locked_until=timezone.now() + timedelta(seconds=45),
                    expires_at=timezone.now() + ttl,
                )
        except IntegrityError:
            record = IdempotencyKey.objects.select_for_update().get(
                scope_type=scope_type,
                scope_id=scope_id,
                key=key,
            )
    if record.request_hash != fingerprint:
        raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
    if record.response_body is not None:
        return record, dict(record.response_body)
    return record, None


def complete_idempotency(record: IdempotencyKey, response: dict[str, Any]) -> None:
    record.response_status = 200
    record.response_body = _json_safe(response)
    record.locked_until = None
    record.save(update_fields=["response_status", "response_body", "locked_until"])
