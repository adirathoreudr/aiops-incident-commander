"""
executor/audit.py
Audit writer and reader for the executor.

This mirrors agent/audit.py deliberately. The two services build from separate
Docker contexts (each Dockerfile copies only its own directory), so neither can
import from the other; the storage contract is the shared thing, not the code.
If the build contexts are ever unified, these two modules should collapse into
one package.

## Storage contract

The log for an incident is a Redis **list** at ``audit:<incident_id>``, one
JSON-encoded entry per element, oldest first.

A list rather than a JSON blob because the agent and the executor both write to
the same key from separate processes. Read-modify-write (GET, append, SET) loses
an entry whenever the two interleave. RPUSH is atomic, so concurrent writers
cannot clobber each other.

Every entry carries ``ts``, ``incident_id`` and an ``event_type`` drawn from
EVENT_TYPES — the dashboard switches on event_type to decide what to render, so
an entry without one reaches the operator as a blank row.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

log = logging.getLogger("executor.audit")

AUDIT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

EVENT_REASONING_COMPLETE = "reasoning_complete"
EVENT_ACTION_EXECUTED = "action_executed"
EVENT_APPROVAL_DECISION = "approval_decision"

EVENT_TYPES = frozenset(
    {EVENT_REASONING_COMPLETE, EVENT_ACTION_EXECUTED, EVENT_APPROVAL_DECISION}
)

# Written by the collector. The executor reads it to serve the global audit
# feed in newest-first order without scanning the keyspace.
INCIDENT_INDEX_KEY = "incidents:index"


def audit_key(incident_id: str) -> str:
    return f"audit:{incident_id}"


async def read_audit(redis: aioredis.Redis, incident_id: str) -> list[dict]:
    """
    Return an incident's audit entries, oldest first.

    Handles keys still written in the pre-list format: LRANGE against a string
    raises WRONGTYPE, so fall back to parsing the old JSON blob rather than
    showing an operator an empty compliance record.
    """
    key = audit_key(incident_id)
    try:
        raw_entries = await redis.lrange(key, 0, -1)
    except ResponseError:
        legacy = await redis.get(key)
        if not legacy:
            return []
        try:
            return json.loads(legacy)
        except json.JSONDecodeError:
            log.warning("Unparseable legacy audit blob at %s", key)
            return []

    entries = []
    for raw in raw_entries:
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            log.warning("Skipping unparseable audit entry in %s", key)
    return entries


async def read_recent_audit(redis: aioredis.Redis, limit: int = 50) -> list[dict]:
    """
    Return audit entries across all known incidents, newest first.

    Walks the collector's incident index rather than scanning audit:* — KEYS is
    O(N) and blocks the server, which is the wrong behaviour for a page an
    operator opens during an incident.
    """
    # Read from more incidents than the entry limit, because a single busy
    # incident can easily produce more than `limit` entries on its own. Taking
    # the newest `limit` incidents and then the newest `limit` entries would let
    # one noisy incident fill the whole page and hide every other one — an
    # "all events" view that silently shows a single incident is worse than a
    # short one.
    incident_ids = await redis.zrevrange(
        INCIDENT_INDEX_KEY, 0, max(limit * 4 - 1, 0)
    )

    entries: list[dict] = []
    for incident_id in incident_ids:
        entries.extend(await read_audit(redis, incident_id))

    entries.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return entries[:limit]


class AuditLogger:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def _append(self, incident_id: str, entry: dict[str, Any]) -> None:
        key = audit_key(incident_id)
        await self._redis.rpush(key, json.dumps(entry))
        await self._redis.expire(key, AUDIT_TTL_SECONDS)

    async def record_action(
        self,
        incident_id: str,
        action_type: str,
        target: str,
        actor: str,
        success: bool,
        result: str,
        params: dict | None = None,
        recovered: bool | None = None,
    ) -> None:
        await self._append(
            incident_id,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "incident_id": incident_id,
                "event_type": EVENT_ACTION_EXECUTED,
                "action_type": action_type,
                "target": target,
                "params": params or {},
                "actor": actor,
                "success": success,
                "result": result,
                "recovered": recovered,
            },
        )

    async def record_approval(
        self,
        incident_id: str,
        approved: bool,
        approver: str,
        action_type: str | None,
    ) -> None:
        await self._append(
            incident_id,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "incident_id": incident_id,
                "event_type": EVENT_APPROVAL_DECISION,
                "approved": approved,
                "approver": approver,
                "action_type": action_type,
            },
        )
