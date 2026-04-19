"""
agent/audit.py
Append-only audit log. Every prompt, decision, action, and outcome is
stored in Redis with a TTL and can be retrieved for compliance review.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

log = logging.getLogger("agent.audit")

AUDIT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


class AuditLogger:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def record(self, incident_id: str, incident: dict[str, Any]) -> None:
        """Append a reasoning outcome to the audit log for this incident."""
        entry = {
            "ts":               datetime.now(timezone.utc).isoformat(),
            "incident_id":      incident_id,
            "status":           incident.get("status"),
            "incident_type":    incident.get("incident_type"),
            "probable_root_cause": incident.get("probable_root_cause"),
            "confidence_score": incident.get("confidence_score"),
            "recommended_action": incident.get("recommended_action"),
            "requires_approval": incident.get("requires_approval"),
            "supporting_evidence": incident.get("supporting_evidence", []),
        }

        key = f"audit:{incident_id}"
        raw = await self._redis.get(key)
        existing: list[dict] = json.loads(raw) if raw else []
        existing.append(entry)

        await self._redis.setex(key, AUDIT_TTL_SECONDS, json.dumps(existing))
        log.info("Audit recorded for incident %s (entries=%d)", incident_id, len(existing))

    async def record_action(
        self,
        incident_id: str,
        action_type: str,
        target: str,
        params: dict,
        success: bool,
        result: str,
        actor: str = "executor",
    ) -> None:
        """Record a remediation action execution."""
        entry = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "incident_id": incident_id,
            "event_type":  "action_executed",
            "action_type": action_type,
            "target":      target,
            "params":      params,
            "actor":       actor,
            "success":     success,
            "result":      result,
        }

        key = f"audit:{incident_id}"
        raw = await self._redis.get(key)
        existing: list[dict] = json.loads(raw) if raw else []
        existing.append(entry)

        await self._redis.setex(key, AUDIT_TTL_SECONDS, json.dumps(existing))

    async def record_approval(
        self,
        incident_id: str,
        approved: bool,
        approver: str,
        action_type: str,
    ) -> None:
        entry = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "incident_id": incident_id,
            "event_type":  "approval_decision",
            "approved":    approved,
            "approver":    approver,
            "action_type": action_type,
        }
        key = f"audit:{incident_id}"
        raw = await self._redis.get(key)
        existing: list[dict] = json.loads(raw) if raw else []
        existing.append(entry)
        await self._redis.setex(key, AUDIT_TTL_SECONDS, json.dumps(existing))
