from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from identity.models import User
from organizations.models import Office
from organizations.services import require_fresh_mfa
from policies.configuration import CONFIGURATION_REGISTRY, definition_for, validate_value
from policies.models import ConfigurationValue, PolicyAcceptance, PolicyTemplate, PolicyVersion


def _content_hash(*, content: str, rules: object) -> str:
    payload = f"{content}\n{rules!r}".encode()
    return hashlib.sha256(payload).hexdigest()


def _request_hash(request: HttpRequest, header: str) -> bytes | None:
    value = request.META.get(header)
    return hashlib.sha256(value.encode()).digest() if value else None


def _office_from_public_id(public_id: str | None) -> Office | None:
    if not public_id:
        return None
    office = Office.objects.filter(public_id=public_id).first()
    if office is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "office_id", "reason": "not_found"}],
        )
    return office


@transaction.atomic
def create_policy_version(
    *, actor: User, request: HttpRequest, data: dict[str, Any], idempotency_key: str
) -> tuple[PolicyVersion, dict[str, Any] | None]:
    require_fresh_mfa(request)
    record, replay = begin_idempotency(
        scope_type="platform_policy_version",
        scope_id=actor.id,
        key=idempotency_key,
        payload=data,
    )
    if replay is not None:
        policy = PolicyVersion.objects.select_related("template", "office").get(id=replay["id"])
        return policy, replay
    owner_scope = str(data["owner_scope"])
    office = _office_from_public_id(str(data.get("office_id") or "") or None)
    if owner_scope == PolicyTemplate.OwnerScope.PLATFORM and office is not None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "office_id", "reason": "platform_policy_must_be_global"}],
        )
    if owner_scope == PolicyTemplate.OwnerScope.OFFICE and office is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "office_id", "reason": "required_for_office_policy"}],
        )
    effective_from = data["effective_from"]
    effective_to = data.get("effective_to")
    if effective_to is not None and effective_to <= effective_from:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "effective_to", "reason": "must_be_after_effective_from"}],
        )

    template, _ = PolicyTemplate.objects.update_or_create(
        code=str(data["code"]).strip(),
        defaults={
            "policy_type": data["policy_type"],
            "owner_scope": owner_scope,
            "status": PolicyTemplate.Status.ACTIVE,
        },
    )
    latest = (
        PolicyVersion.objects.select_for_update()
        .filter(template=template, office=office, language=data.get("language", "ar"))
        .order_by("-version_no")
        .first()
    )
    version_no = 1 if latest is None else latest.version_no + 1
    content = str(data["content_markdown"])
    rules = data.get("rules_json", {})
    policy = PolicyVersion.objects.create(
        template=template,
        office=office,
        version_no=version_no,
        language=str(data.get("language", "ar")),
        title=str(data["title"]).strip(),
        content_markdown=content,
        rules_json=rules,
        effective_from=effective_from,
        effective_to=effective_to,
        published_at=timezone.now() if data.get("publish", True) else None,
        content_sha256=_content_hash(content=content, rules=rules),
    )
    record_audit(
        action="platform.policy.version.create",
        object_type="policy_version",
        object_id=policy.id,
        actor_user=actor,
        office_id=office.id if office else None,
        request=request,
        after={
            "code": template.code,
            "version_no": version_no,
            "office_id": office.public_id if office else None,
            "published": policy.published_at is not None,
            "content_sha256": policy.content_sha256,
        },
    )
    response = {"id": str(policy.id)}
    complete_idempotency(record, response)
    OutboxEvent.objects.create(
        aggregate_type="policy_version",
        aggregate_id=policy.id,
        event_type="policy.version.published" if policy.published_at else "policy.version.created",
        payload={
            "policy_version_id": str(policy.id),
            "template_code": template.code,
            "version_no": version_no,
            "language": policy.language,
            "effective_from": policy.effective_from.isoformat(),
        },
    )
    return policy, None


def _effective_queryset(*, office: Office, at: datetime):  # type: ignore[no-untyped-def]
    return PolicyVersion.objects.select_related("template", "office").filter(
        template__status=PolicyTemplate.Status.ACTIVE,
        published_at__isnull=False,
        effective_from__lte=at,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at)).filter(
        Q(office=office) | Q(office__isnull=True)
    )


def resolve_policy_snapshot(
    *,
    office: Office,
    selected_ids: Iterable[str | uuid.UUID] | None,
    required_types: Iterable[str],
    at: datetime | None = None,
) -> tuple[dict[str, object], list[str]]:
    effective_at = at or timezone.now()
    queryset = _effective_queryset(office=office, at=effective_at)
    selected = [str(value) for value in (selected_ids or [])]
    if selected:
        queryset = queryset.filter(id__in=selected)

    candidates = list(queryset.order_by("template__policy_type", "-office_id", "-version_no"))
    by_type: dict[str, PolicyVersion] = {}
    for version in candidates:
        policy_type = version.template.policy_type
        current = by_type.get(policy_type)
        if current is None or (current.office_id is None and version.office_id == office.id):
            by_type[policy_type] = version

    required = list(required_types)
    missing = [policy_type for policy_type in required if policy_type not in by_type]
    snapshot: dict[str, object] = {}
    for policy_type, version in by_type.items():
        snapshot[policy_type] = {
            "id": str(version.id),
            "code": version.template.code,
            "version_no": version.version_no,
            "language": version.language,
            "title": version.title,
            "rules": version.rules_json,
            "content_sha256": version.content_sha256,
            "effective_from": version.effective_from.isoformat(),
            "office_id": str(version.office_id) if version.office_id else None,
        }
    return snapshot, missing


def get_public_policy(*, code: str, office: Office | None = None) -> PolicyVersion:
    now = timezone.now()
    queryset = PolicyVersion.objects.select_related("template", "office").filter(
        template__code=code,
        template__status=PolicyTemplate.Status.ACTIVE,
        published_at__isnull=False,
        effective_from__lte=now,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=now))
    policy: PolicyVersion | None = None
    if office is not None:
        policy = queryset.filter(office=office).order_by("-version_no").first()
    if policy is None:
        policy = queryset.filter(office__isnull=True).order_by("-version_no").first()
    if policy is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return policy


def record_policy_acceptances(
    *,
    policy_version_ids: Iterable[str | uuid.UUID],
    subject_type: str,
    subject_id: uuid.UUID,
    accepted_by_user: User | None,
    request: HttpRequest,
) -> list[PolicyAcceptance]:
    requested_values = list(policy_version_ids)
    versions = list(PolicyVersion.objects.filter(id__in=requested_values))
    requested = {str(item) for item in requested_values}
    if {str(item.id) for item in versions} != requested:
        raise DomainAPIException("POLICY_ACCEPTANCE_REQUIRED")
    acceptances: list[PolicyAcceptance] = []
    for version in versions:
        acceptance, _ = PolicyAcceptance.objects.get_or_create(
            policy_version=version,
            subject_type=subject_type,
            subject_id=subject_id,
            defaults={
                "accepted_by_user": accepted_by_user,
                "ip_hash": _request_hash(request, "REMOTE_ADDR"),
                "user_agent_hash": _request_hash(request, "HTTP_USER_AGENT"),
            },
        )
        acceptances.append(acceptance)
    return acceptances


def _effective_configuration_row(
    *, scope_type: str, scope_id: uuid.UUID | None, key: str, at: datetime
) -> ConfigurationValue | None:
    return (
        ConfigurationValue.objects.filter(
            scope_type=scope_type,
            scope_id=scope_id,
            key=key,
            approved_by__isnull=False,
            effective_from__lte=at,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at))
        .order_by("-effective_from", "-created_at")
        .first()
    )


def effective_configuration(
    *, scope_type: str, scope_id: uuid.UUID | None = None, at: datetime | None = None
) -> dict[str, Any]:
    current = at or timezone.now()
    result: dict[str, Any] = {}
    for key, definition in CONFIGURATION_REGISTRY.items():
        if scope_type not in definition.scopes:
            continue
        row = _effective_configuration_row(scope_type=scope_type, scope_id=scope_id, key=key, at=current)
        if row is None and scope_type != ConfigurationValue.ScopeType.PLATFORM:
            row = _effective_configuration_row(
                scope_type=ConfigurationValue.ScopeType.PLATFORM,
                scope_id=None,
                key=key,
                at=current,
            )
        result[key] = {
            "value": row.value_json if row is not None else definition.default,
            "value_type": definition.value_type,
            "source": "override" if row is not None else "default",
            "effective_from": row.effective_from if row is not None else None,
            "snapshot": definition.snapshot,
            "bounds": {
                "minimum": str(definition.minimum) if definition.minimum is not None else None,
                "maximum": str(definition.maximum) if definition.maximum is not None else None,
                "choices": sorted(definition.choices) if definition.choices is not None else None,
            },
        }
    return result


def _configuration_before(*, scope_type: str, scope_id: uuid.UUID | None, key: str, at: datetime) -> object:
    row = _effective_configuration_row(scope_type=scope_type, scope_id=scope_id, key=key, at=at)
    return row.value_json if row is not None else definition_for(key, scope_type).default


@transaction.atomic
def propose_configuration_changes(
    *,
    scope_type: str,
    scope_id: uuid.UUID | None,
    actor: User,
    request: HttpRequest,
    changes: dict[str, Any],
    reason: str,
    effective_from: datetime,
    idempotency_key: str,
    auto_approve: bool,
) -> list[ConfigurationValue]:
    require_fresh_mfa(request)
    if not reason.strip():
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "reason", "reason": "required"}])
    record, replay = begin_idempotency(
        scope_type=f"{scope_type}_configuration",
        scope_id=scope_id or actor.id,
        key=idempotency_key,
        payload={"changes": changes, "reason": reason, "effective_from": effective_from},
    )
    if replay is not None:
        ids = replay.get("change_ids", [])
        return list(ConfigurationValue.objects.filter(id__in=ids).order_by("created_at"))
    if not changes:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "changes", "reason": "required"}])
    created: list[ConfigurationValue] = []
    now = timezone.now()
    for key, raw_value in changes.items():
        definition = definition_for(key, scope_type)
        value = validate_value(definition=definition, value=raw_value)
        row = ConfigurationValue.objects.create(
            scope_type=scope_type,
            scope_id=scope_id,
            key=key,
            value_json=value,
            value_type=definition.value_type,
            effective_from=max(effective_from, now),
            created_by=actor,
            approved_by=actor if auto_approve else None,
            reason=reason.strip(),
        )
        if auto_approve:
            previous = (
                ConfigurationValue.objects.select_for_update()
                .filter(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    key=key,
                    approved_by__isnull=False,
                    effective_to__isnull=True,
                )
                .exclude(id=row.id)
                .order_by("-effective_from")
                .first()
            )
            before = previous.value_json if previous is not None else definition.default
            if previous is not None:
                previous.effective_to = row.effective_from
                previous.save(update_fields=["effective_to"])
            record_audit(
                action=f"{scope_type}.configuration.approve",
                object_type="configuration_value",
                object_id=row.id,
                actor_user=actor,
                office_id=scope_id if scope_type == ConfigurationValue.ScopeType.OFFICE else None,
                request=request,
                before={"key": key, "value": before},
                after={"key": key, "value": value, "effective_from": row.effective_from.isoformat()},
                reason_code=reason.strip(),
            )
        else:
            record_audit(
                action="platform.configuration.propose",
                object_type="configuration_value",
                object_id=row.id,
                actor_user=actor,
                request=request,
                before={
                    "key": key,
                    "value": _configuration_before(
                        scope_type=scope_type,
                        scope_id=scope_id,
                        key=key,
                        at=now,
                    ),
                },
                after={
                    "key": key,
                    "value": value,
                    "effective_from": row.effective_from.isoformat(),
                    "status": "pending_approval",
                },
                reason_code=reason.strip(),
            )
        created.append(row)
    complete_idempotency(record, {"change_ids": [str(item.id) for item in created]})
    return created


@transaction.atomic
def approve_configuration_changes(
    *, actor: User, request: HttpRequest, change_ids: list[uuid.UUID], reason: str, idempotency_key: str
) -> list[ConfigurationValue]:
    require_fresh_mfa(request)
    record, replay = begin_idempotency(
        scope_type="platform_configuration_approval",
        scope_id=actor.id,
        key=idempotency_key,
        payload={"change_ids": [str(item) for item in change_ids], "reason": reason},
    )
    if replay is not None:
        return list(ConfigurationValue.objects.filter(id__in=replay.get("change_ids", [])))
    rows = list(ConfigurationValue.objects.select_for_update().filter(id__in=change_ids))
    if len(rows) != len(set(change_ids)):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    for row in rows:
        if row.scope_type != ConfigurationValue.ScopeType.PLATFORM or row.approved_by_id is not None:
            raise DomainAPIException("CONFLICT", details={"reason": "configuration_not_pending"})
        if row.created_by_id == actor.id:
            raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
        previous = (
            ConfigurationValue.objects.select_for_update()
            .filter(
                scope_type=row.scope_type,
                scope_id=row.scope_id,
                key=row.key,
                approved_by__isnull=False,
                effective_to__isnull=True,
            )
            .exclude(id=row.id)
            .order_by("-effective_from")
            .first()
        )
        before = previous.value_json if previous is not None else definition_for(row.key, row.scope_type).default
        if previous is not None:
            previous.effective_to = row.effective_from
            previous.save(update_fields=["effective_to"])
        row.approved_by = actor
        row.save(update_fields=["approved_by"])
        record_audit(
            action="platform.configuration.approve",
            object_type="configuration_value",
            object_id=row.id,
            actor_user=actor,
            request=request,
            before={"key": row.key, "value": before},
            after={"key": row.key, "value": row.value_json, "effective_from": row.effective_from.isoformat()},
            reason_code=reason.strip() or row.reason,
            metadata={"created_by": str(row.created_by_id), "approved_by": str(actor.id)},
        )
        OutboxEvent.objects.create(
            aggregate_type="configuration_value",
            aggregate_id=row.id,
            event_type="configuration.changed",
            payload={"key": row.key, "scope_type": row.scope_type, "effective_from": row.effective_from.isoformat()},
        )
    complete_idempotency(record, {"change_ids": [str(item.id) for item in rows]})
    return rows
