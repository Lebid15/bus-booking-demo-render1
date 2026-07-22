from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from common.exceptions import DomainAPIException
from policies.models import ConfigurationValue


@dataclass(frozen=True)
class ConfigurationDefinition:
    key: str
    scopes: frozenset[str]
    value_type: str
    default: object
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    choices: frozenset[str] | None = None
    sensitive: bool = False
    snapshot: bool = False


CONFIGURATION_REGISTRY: dict[str, ConfigurationDefinition] = {
    "platform.booking.default_hold_minutes": ConfigurationDefinition(
        key="platform.booking.default_hold_minutes",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=10,
        minimum=Decimal("1"),
        maximum=Decimal("60"),
    ),
    "platform.booking.max_unpaid_per_phone": ConfigurationDefinition(
        key="platform.booking.max_unpaid_per_phone",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=3,
        minimum=Decimal("1"),
        maximum=Decimal("20"),
    ),
    "office.payment.deadline_minutes": ConfigurationDefinition(
        key="office.payment.deadline_minutes",
        scopes=frozenset({ConfigurationValue.ScopeType.OFFICE}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=120,
        minimum=Decimal("15"),
        maximum=Decimal("1440"),
        sensitive=True,
        snapshot=True,
    ),
    "office.boarding.open_minutes": ConfigurationDefinition(
        key="office.boarding.open_minutes",
        scopes=frozenset({ConfigurationValue.ScopeType.OFFICE}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=60,
        minimum=Decimal("30"),
        maximum=Decimal("180"),
        sensitive=True,
        snapshot=True,
    ),
    "office.boarding.close_minutes": ConfigurationDefinition(
        key="office.boarding.close_minutes",
        scopes=frozenset({ConfigurationValue.ScopeType.OFFICE}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=10,
        minimum=Decimal("5"),
        maximum=Decimal("30"),
        sensitive=True,
        snapshot=True,
    ),
    "office.manual_payment.methods": ConfigurationDefinition(
        key="office.manual_payment.methods",
        scopes=frozenset({ConfigurationValue.ScopeType.OFFICE}),
        value_type=ConfigurationValue.ValueType.LIST,
        default=["cash", "transfer"],
        choices=frozenset({"cash", "transfer", "electronic"}),
        sensitive=True,
        snapshot=True,
    ),
    "platform.gender_adjacency.enabled": ConfigurationDefinition(
        key="platform.gender_adjacency.enabled",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.BOOLEAN,
        default=True,
        sensitive=True,
    ),
    "platform.refund.dual_approval_threshold": ConfigurationDefinition(
        key="platform.refund.dual_approval_threshold",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.DECIMAL,
        default="500000.00",
        minimum=Decimal("0"),
        sensitive=True,
    ),
    "platform.settlement.cadence": ConfigurationDefinition(
        key="platform.settlement.cadence",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM, ConfigurationValue.ScopeType.OFFICE}),
        value_type=ConfigurationValue.ValueType.STRING,
        default="monthly",
        choices=frozenset({"weekly", "monthly"}),
        sensitive=True,
    ),
    "platform.offline_manifest.ttl_hours": ConfigurationDefinition(
        key="platform.offline_manifest.ttl_hours",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=12,
        minimum=Decimal("2"),
        maximum=Decimal("24"),
        sensitive=True,
    ),
    "platform.notifications.email_enabled": ConfigurationDefinition(
        key="platform.notifications.email_enabled",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.BOOLEAN,
        default=True,
    ),
    "platform.notifications.sms_enabled": ConfigurationDefinition(
        key="platform.notifications.sms_enabled",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.BOOLEAN,
        default=False,
    ),
    "platform.risk.manual_review_threshold": ConfigurationDefinition(
        key="platform.risk.manual_review_threshold",
        scopes=frozenset({ConfigurationValue.ScopeType.PLATFORM}),
        value_type=ConfigurationValue.ValueType.INTEGER,
        default=50,
        minimum=Decimal("0"),
        maximum=Decimal("100"),
        sensitive=True,
    ),
}


def definition_for(key: str, scope_type: str) -> ConfigurationDefinition:
    definition = CONFIGURATION_REGISTRY.get(key)
    if definition is None or scope_type not in definition.scopes:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": f"changes.{key}", "reason": "unknown_or_forbidden_configuration_key"}],
        )
    return definition


def validate_value(*, definition: ConfigurationDefinition, value: Any) -> object:
    value_type = definition.value_type
    normalized: object
    try:
        if value_type == ConfigurationValue.ValueType.BOOLEAN:
            if not isinstance(value, bool):
                raise TypeError
            normalized = value
        elif value_type in {ConfigurationValue.ValueType.INTEGER, ConfigurationValue.ValueType.DURATION}:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError
            normalized = value
        elif value_type == ConfigurationValue.ValueType.DECIMAL:
            if isinstance(value, bool):
                raise TypeError
            normalized = str(Decimal(str(value)).quantize(Decimal("0.01")))
        elif value_type == ConfigurationValue.ValueType.STRING:
            if not isinstance(value, str):
                raise TypeError
            normalized = value.strip()
        elif value_type == ConfigurationValue.ValueType.LIST:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise TypeError
            normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        elif value_type == ConfigurationValue.ValueType.OBJECT:
            if not isinstance(value, dict):
                raise TypeError
            normalized = value
        else:
            raise TypeError
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": definition.key, "reason": f"expected_{value_type}"}],
        ) from exc

    numeric: Decimal | None = None
    if value_type in {
        ConfigurationValue.ValueType.INTEGER,
        ConfigurationValue.ValueType.DURATION,
        ConfigurationValue.ValueType.DECIMAL,
    }:
        numeric = Decimal(str(normalized))
    if numeric is not None and definition.minimum is not None and numeric < definition.minimum:
        raise DomainAPIException(
            "CONFIGURATION_OUT_OF_RANGE",
            details={"key": definition.key, "minimum": str(definition.minimum), "maximum": str(definition.maximum)},
        )
    if numeric is not None and definition.maximum is not None and numeric > definition.maximum:
        raise DomainAPIException(
            "CONFIGURATION_OUT_OF_RANGE",
            details={"key": definition.key, "minimum": str(definition.minimum), "maximum": str(definition.maximum)},
        )
    if definition.choices is not None:
        selected = set(normalized) if isinstance(normalized, list) else {str(normalized)}
        if not selected or not selected.issubset(definition.choices):
            raise DomainAPIException(
                "CONFIGURATION_OUT_OF_RANGE",
                details={"key": definition.key, "allowed": sorted(definition.choices)},
            )
    return normalized
