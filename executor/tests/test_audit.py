"""
Tests for executor/audit.py — the executor's half of the audit trail.

The executor owns the reads the dashboard uses, including the global feed on the
audit page. That feed walks the collector's incident index rather than scanning
audit:* with KEYS, because KEYS is O(N) and blocks the server — the wrong
behaviour for a page an operator opens in the middle of an incident.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
from redis.exceptions import ResponseError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from executor.audit import (  # noqa: E402
    INCIDENT_INDEX_KEY,
    AuditLogger,
    read_audit,
    read_recent_audit,
)


class FakeRedis:
    """Stateful stand-in covering the commands the audit reader uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.zsets: dict[str, list[str]] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def rpush(self, key: str, *values: str):
        if key in self.store:
            raise ResponseError("WRONGTYPE")
        await asyncio.sleep(0)
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    async def lrange(self, key: str, start: int, end: int):
        if key in self.store:
            raise ResponseError("WRONGTYPE")
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    async def expire(self, key: str, ttl: int):
        self.expirations[key] = ttl
        return True

    async def zrevrange(self, key: str, start: int, end: int):
        items = self.zsets.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]


@pytest.fixture
def redis():
    return FakeRedis()


class TestPerIncidentAudit:
    async def test_action_and_approval_both_recorded(self, redis):
        logger = AuditLogger(redis)

        await logger.record_approval(
            "inc-1", approved=True, approver="operator", action_type="scale_up"
        )
        await logger.record_action(
            "inc-1",
            action_type="scale_up",
            target="orders/order-service",
            actor="executor",
            success=True,
            result="Scaled to 7 replicas",
            recovered=True,
        )

        entries = await read_audit(redis, "inc-1")

        assert [e["event_type"] for e in entries] == [
            "approval_decision",
            "action_executed",
        ]
        assert entries[1]["recovered"] is True
        assert entries[1]["target"] == "orders/order-service"

    async def test_reads_legacy_blob_format(self, redis):
        redis.store["audit:inc-old"] = json.dumps(
            [{"ts": "2026-07-25T10:00:00+00:00", "event_type": "action_executed"}]
        )

        entries = await read_audit(redis, "inc-old")

        assert len(entries) == 1


class TestGlobalFeed:
    async def test_returns_entries_across_incidents_newest_first(self, redis):
        redis.zsets[INCIDENT_INDEX_KEY] = ["inc-new", "inc-old"]
        redis.lists["audit:inc-old"] = [
            json.dumps({"ts": "2026-07-25T09:00:00+00:00", "event_type": "a"})
        ]
        redis.lists["audit:inc-new"] = [
            json.dumps({"ts": "2026-07-25T11:00:00+00:00", "event_type": "b"})
        ]

        entries = await read_recent_audit(redis, limit=10)

        assert [e["event_type"] for e in entries] == ["b", "a"]

    async def test_respects_the_limit(self, redis):
        redis.zsets[INCIDENT_INDEX_KEY] = ["inc-1"]
        redis.lists["audit:inc-1"] = [
            json.dumps({"ts": f"2026-07-25T10:0{i}:00+00:00", "event_type": "x"})
            for i in range(5)
        ]

        assert len(await read_recent_audit(redis, limit=3)) == 3

    async def test_empty_index_yields_no_entries(self, redis):
        assert await read_recent_audit(redis, limit=10) == []

    async def test_incident_without_audit_entries_is_skipped(self, redis):
        redis.zsets[INCIDENT_INDEX_KEY] = ["inc-untouched"]

        assert await read_recent_audit(redis, limit=10) == []


class TestGlobalFeedFairness:
    async def test_a_busy_incident_does_not_hide_the_others(self, redis):
        """
        One noisy incident used to fill the whole page: the reader took the
        newest `limit` incidents and then the newest `limit` entries, so an
        incident with more than `limit` entries of its own crowded out every
        other one. An "all events" view showing a single incident is worse than
        a short one.
        """
        redis.zsets[INCIDENT_INDEX_KEY] = ["inc-noisy", "inc-quiet"]
        redis.lists["audit:inc-noisy"] = [
            json.dumps({"ts": f"2026-07-26T10:{i:02d}:00+00:00", "incident_id": "inc-noisy"})
            for i in range(30)
        ]
        redis.lists["audit:inc-quiet"] = [
            json.dumps({"ts": "2026-07-26T11:00:00+00:00", "incident_id": "inc-quiet"})
        ]

        entries = await read_recent_audit(redis, limit=10)
        seen = {e["incident_id"] for e in entries}

        assert "inc-quiet" in seen, "the quieter incident was crowded out entirely"
        assert entries[0]["incident_id"] == "inc-quiet", "newest entry should lead"
