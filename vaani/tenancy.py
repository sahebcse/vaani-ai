"""Multi-tenancy: tenant registry with per-tenant voice/language config."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tenant:
    id: str
    display_name: str
    allowed_languages: list[str] = field(default_factory=lambda: ["hi", "en"])
    voice: str = "default"


class DuplicateTenantError(Exception):
    """Raised when creating a tenant that already exists."""


class TenantStore:
    def get(self, tenant_id: str) -> Tenant | None:
        raise NotImplementedError

    def list_all(self) -> list[Tenant]:
        raise NotImplementedError

    def create(self, tenant: Tenant) -> Tenant:
        raise NotImplementedError

    def set_voice(self, tenant_id: str, voice: str) -> Tenant | None:
        raise NotImplementedError


class InMemoryTenantStore(TenantStore):
    def __init__(self, tenants: list[Tenant] | None = None) -> None:
        self._tenants: dict[str, Tenant] = {t.id: t for t in (tenants or [])}

    def get(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_all(self) -> list[Tenant]:
        return sorted(self._tenants.values(), key=lambda t: t.id)

    def create(self, tenant: Tenant) -> Tenant:
        if tenant.id in self._tenants:
            raise DuplicateTenantError(tenant.id)
        self._tenants[tenant.id] = tenant
        return tenant

    def set_voice(self, tenant_id: str, voice: str) -> Tenant | None:
        current = self._tenants.get(tenant_id)
        if current is None:
            return None
        updated = Tenant(
            id=current.id,
            display_name=current.display_name,
            allowed_languages=current.allowed_languages,
            voice=voice,
        )
        self._tenants[tenant_id] = updated
        return updated
