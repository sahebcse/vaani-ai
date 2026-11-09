"""Demo-grade signed tokens + RBAC (swap for an IdP in production).

Token shape: base64url(header).base64url(payload).base64url(hmac-sha256).
Payload: {tenant, role, exp}. Roles: admin (manage), viewer (read-only).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    tenant: str
    role: str


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or forged."""


ADMIN_ROLE = "admin"
VIEWER_ROLE = "viewer"
_ROLES = (ADMIN_ROLE, VIEWER_ROLE)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(tenant: str, role: str, secret: str, ttl_seconds: int = 3600) -> str:
    header = _b64encode(json.dumps({"alg": "HS256"}).encode())
    payload = _b64encode(
        json.dumps({"tenant": tenant, "role": role, "exp": int(time.time()) + ttl_seconds}).encode()
    )
    sig = _b64encode(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def verify_token(token: str, secret: str) -> Principal:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("malformed token")
    header, payload, sig = parts
    expected = _b64encode(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected):
        raise AuthError("bad signature")
    try:
        claims = json.loads(_b64decode(payload))
    except ValueError:
        raise AuthError("bad payload") from None
    if not isinstance(claims, dict):
        raise AuthError("bad payload")
    if int(claims.get("exp", 0)) < int(time.time()):
        raise AuthError("expired token")
    role = str(claims.get("role", ""))
    if role not in _ROLES:
        raise AuthError("unknown role")
    return Principal(tenant=str(claims.get("tenant", "")), role=role)
