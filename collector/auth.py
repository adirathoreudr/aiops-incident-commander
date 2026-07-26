"""
collector/auth.py
Bearer-token authentication for the collector's write paths.

## Why the collector needs this at all

The collector does not touch the cluster, so it looks read-only. It isn't:
/webhook/simulate injects a synthetic incident straight onto the agent queue,
and a high-confidence incident in a permitted namespace is auto-executed without
a human ever seeing it. Left open, it is a remote "restart this deployment"
button wearing a test-fixture label.

## Two different doors, two different defaults

/webhook/simulate is an operator tool and fails closed, like the executor's
mutating endpoints: no token configured means no injection.

/webhook/alertmanager is called by Alertmanager itself, which needs matching
config to send a credential. Requiring a token unconditionally would silently
stop ingesting real alerts on upgrade — the platform would look healthy and
quietly see nothing, which is worse than the exposure it closes. So it is
enforced only once COLLECTOR_API_TOKEN is set, and the startup log says plainly
which mode is active.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger("collector.auth")

API_TOKEN = os.getenv("COLLECTOR_API_TOKEN", "")

_bearer = HTTPBearer(auto_error=False, description="Collector API token")


def log_auth_status() -> None:
    if API_TOKEN:
        log.info(
            "Collector API token configured — /webhook/simulate and "
            "/webhook/alertmanager require authentication"
        )
    else:
        log.warning(
            "COLLECTOR_API_TOKEN is not set. /webhook/simulate will refuse "
            "every request; /webhook/alertmanager stays open so real alert "
            "ingestion is not silently broken. Set the variable to "
            "authenticate both."
        )


def _check(credentials: HTTPAuthorizationCredentials | None) -> None:
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, API_TOKEN
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Fail closed — used for operator-facing write paths."""
    if not API_TOKEN:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Collector is not configured to accept injected incidents: "
            "COLLECTOR_API_TOKEN is unset.",
        )
    _check(credentials)


async def require_token_if_configured(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """
    Enforce a token only when one is configured.

    Used for the Alertmanager webhook, where failing closed on an unset token
    would stop the platform seeing production alerts at all.
    """
    if not API_TOKEN:
        return
    _check(credentials)
