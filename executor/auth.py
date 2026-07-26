"""
executor/auth.py
Bearer-token authentication for the endpoints that change a cluster.

## Why this exists

/approve and /execute/manual patch live Kubernetes deployments. They had no
authentication of any kind, and CORS was open to every origin, so anyone who
could reach the executor could restart or rescale a workload. The policy engine
limits *what* can be done; it says nothing about *who* may ask.

## Why it fails closed

If EXECUTOR_API_TOKEN is unset, mutating requests are refused rather than
allowed. An operator who has not configured a token has not authorised anyone to
remediate, and defaulting to "no token means no checks" would leave exactly the
hole this module closes — quietly, and only in the deployments that forgot to
configure it. An unconfigured executor can still ingest, reason and report; it
just cannot act, and it says so loudly at startup and in the 503 body.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger("executor.auth")

API_TOKEN = os.getenv("EXECUTOR_API_TOKEN", "")

# auto_error=False so a missing header reaches our handler and gets the same
# 401 shape as a wrong one, rather than FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False, description="Executor API token")


def log_auth_status() -> None:
    """Announce at startup whether remediation is actually reachable."""
    if API_TOKEN:
        log.info("Executor API token configured — mutating endpoints protected")
    else:
        log.warning(
            "EXECUTOR_API_TOKEN is not set. Mutating endpoints (/approve, "
            "/execute/manual) will refuse every request. Set the variable to "
            "enable remediation."
        )


def _check(credentials: HTTPAuthorizationCredentials | None) -> None:
    """
    Constant-time comparison: a plain == leaks how much of the token matched
    through timing, which over enough requests is enough to recover it.
    """
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, API_TOKEN
    ):
        log.warning("Rejected request with invalid or missing bearer token")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Guard a mutating endpoint. Fails closed when no token is configured."""
    if not API_TOKEN:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Executor is not configured to accept remediation requests: "
            "EXECUTOR_API_TOKEN is unset.",
        )
    _check(credentials)


async def require_token_if_configured(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """
    Guard a read endpoint.

    Reads cannot change the cluster, but audit entries carry root-cause text and
    captured log lines, so they are not public information either. Enforced only
    once a token exists: failing closed here would break the dashboard for any
    deployment that has not configured one, which is a steep price for a read
    path and would push people toward turning the whole thing off.
    """
    if not API_TOKEN:
        return
    _check(credentials)
