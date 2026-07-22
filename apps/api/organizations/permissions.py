from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission

from common.exceptions import DomainAPIException
from identity.models import Permission, PlatformRoleAssignment, User
from organizations.services import require_permission, resolve_office_context


class HasOfficeContext(BasePermission):
    def has_permission(self, request, view):  # type: ignore[no-untyped-def]
        request.office_context = resolve_office_context(request.user)
        required = getattr(view, "required_permission", None)
        if required:
            require_permission(request.office_context, required)
        return True


def platform_permission_codes(user: User) -> frozenset[str]:
    assignments = (
        PlatformRoleAssignment.objects.filter(user=user, revoked_at__isnull=True)
        .select_related("role")
        .prefetch_related("role__permissions")
    )
    if assignments.exists():
        return frozenset(
            code
            for assignment in assignments
            if assignment.role.scope_type == "platform"
            for code in assignment.role.permissions.values_list("code", flat=True)
        )
    # Migration compatibility for existing platform administrators. Production may
    # disable this only after every staff account receives an explicit assignment.
    if getattr(settings, "PLATFORM_RBAC_LEGACY_ADMIN_FALLBACK", True):
        codes = frozenset(Permission.objects.filter(code__startswith="platform.").values_list("code", flat=True))
        return codes or frozenset({"*"})
    return frozenset()


class HasPlatformAccess(BasePermission):
    """Fine-grained platform role gate with explicit separation of duties."""

    def has_permission(self, request, view):  # type: ignore[no-untyped-def]
        user = request.user
        if user is None or not user.is_platform_staff:
            raise DomainAPIException("PERMISSION_DENIED")
        required = getattr(view, "required_permission", None)
        permissions = platform_permission_codes(user)
        request.platform_permissions = permissions
        request.required_platform_permission = required
        if required and required not in permissions and "*" not in permissions:
            raise DomainAPIException("PERMISSION_DENIED")
        return True
