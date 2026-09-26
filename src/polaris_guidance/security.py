from __future__ import annotations

import hmac
import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


def current_principal(x_api_key: str | None = Header(default=None)) -> Principal:
    if os.environ.get("POLARIS_AUTH_MODE", "demo") == "demo":
        return Principal(subject="local-demo", role="admin")

    raw_keys = os.environ.get("POLARIS_API_KEYS_JSON", "{}")
    try:
        keys = json.loads(raw_keys)
    except json.JSONDecodeError:
        raise HTTPException(503, "Authentication configuration is invalid.") from None
    if not isinstance(keys, dict) or not x_api_key:
        raise HTTPException(401, "A valid API key is required.")
    for configured_key, identity in keys.items():
        if hmac.compare_digest(str(configured_key), x_api_key) and isinstance(identity, dict):
            return Principal(
                subject=str(identity.get("subject", "unknown")),
                role=str(identity.get("role", "unknown")),
            )
    raise HTTPException(401, "A valid API key is required.")


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in roles and principal.role != "admin":
            raise HTTPException(403, "This role cannot perform the requested action.")
        return principal

    return dependency
