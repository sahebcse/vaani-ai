"""Admin REST APIs: tenants, voices, tokens, call records.

RBAC: admin role manages; viewer role reads. Bootstrap via X-Admin-Key.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from vaani.auth import ADMIN_ROLE, AuthError, Principal, issue_token, verify_token
from vaani.config import Settings, get_settings
from vaani.ledger import CallLog, CallRecord
from vaani.tenancy import DuplicateTenantError, Tenant, TenantStore

router = APIRouter(prefix="/v1/admin")
security = HTTPBearer(auto_error=False)


class TenantOut(BaseModel):
    id: str
    display_name: str
    allowed_languages: list[str]
    voice: str


class TenantCreate(BaseModel):
    id: str
    display_name: str
    allowed_languages: list[str] = ["hi", "en"]
    voice: str = "default"


class VoiceUpdate(BaseModel):
    voice: str


class TokenRequest(BaseModel):
    tenant: str
    role: Literal["admin", "viewer"]
    ttl_seconds: int = 3600


class TokenResponse(BaseModel):
    token: str


class CallRecordOut(BaseModel):
    call_id: str
    tenant: str
    frames_received: int
    frames_dropped: int
    errors: int
    transcript_chars: int
    escalated: bool


def _settings() -> Settings:
    return get_settings()


def _tenants(request: Request) -> TenantStore:
    tenants: TenantStore = request.app.state.tenants
    return tenants


def _call_log(request: Request) -> CallLog:
    log: CallLog = request.app.state.call_log
    return log


async def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(_settings),
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="missing token")
    try:
        return verify_token(credentials.credentials, settings.admin_key)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def require_admin(
    principal: Principal = Depends(current_principal),
) -> Principal:
    if principal.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="admin only")
    return principal


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(
    principal: Principal = Depends(current_principal),  # noqa: ARG001
    tenants: TenantStore = Depends(_tenants),
) -> list[Tenant]:
    return tenants.list_all()


@router.post("/tenants", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate,
    principal: Principal = Depends(require_admin),  # noqa: ARG001
    tenants: TenantStore = Depends(_tenants),
) -> Tenant:
    try:
        return tenants.create(
            Tenant(
                id=body.id,
                display_name=body.display_name,
                allowed_languages=body.allowed_languages,
                voice=body.voice,
            )
        )
    except DuplicateTenantError:
        raise HTTPException(status_code=409, detail="tenant exists") from None


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: str,
    principal: Principal = Depends(current_principal),  # noqa: ARG001
    tenants: TenantStore = Depends(_tenants),
) -> Tenant:
    tenant = tenants.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="unknown tenant")
    return tenant


@router.put("/tenants/{tenant_id}/voice", response_model=TenantOut)
async def set_voice(
    tenant_id: str,
    body: VoiceUpdate,
    principal: Principal = Depends(require_admin),  # noqa: ARG001
    tenants: TenantStore = Depends(_tenants),
) -> Tenant:
    updated = tenants.set_voice(tenant_id, body.voice)
    if updated is None:
        raise HTTPException(status_code=404, detail="unknown tenant")
    return updated


@router.post("/tokens", response_model=TokenResponse)
async def mint_token(
    body: TokenRequest,
    x_admin_key: str | None = Header(default=None),
    settings: Settings = Depends(_settings),
) -> TokenResponse:
    if x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="admin key required")
    return TokenResponse(
        token=issue_token(body.tenant, body.role, settings.admin_key, body.ttl_seconds)
    )


@router.get("/calls", response_model=list[CallRecordOut])
async def list_calls(
    principal: Principal = Depends(current_principal),  # noqa: ARG001
    log: CallLog = Depends(_call_log),
    limit: int = 50,
) -> list[CallRecord]:
    return log.list_recent(limit)
