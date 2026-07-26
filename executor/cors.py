"""
executor/cors.py
Shared CORS origin resolution.

Every service was mounted with ``allow_origins=["*"]`` alongside
``allow_methods=["*"]``. On a read-only service that is merely untidy; on the
executor it meant any page in any browser could drive a request to a cluster
mutation endpoint using the visitor's network position.

Origins come from CORS_ALLOWED_ORIGINS as a comma-separated list, defaulting to
the local dashboard so development works without configuration.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("cors")

DEFAULT_ORIGINS = "http://localhost:3001,http://127.0.0.1:3001"


def allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    origins = [o.strip() for o in raw.split(",") if o.strip()]

    if "*" in origins:
        # Honoured, because a deployment may genuinely sit behind a gateway that
        # has already done this job — but it should never be the silent default,
        # so make the choice visible in the logs.
        log.warning(
            "CORS_ALLOWED_ORIGINS is '*': every origin may call this service "
            "from a browser. Set an explicit list unless a gateway in front of "
            "this service is already restricting origins."
        )
        return ["*"]

    log.info("CORS allowed origins: %s", origins)
    return origins
