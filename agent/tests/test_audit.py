"""
Regression tests for agent/audit.py::AuditLogger.

Two properties the audit trail has to hold, both of which it previously failed.

1. Every entry carries an ``event_type``. The dashboard switches on it
   (ui/src/components/AuditTimeline.tsx, EVENT_STYLES) to decide what to render,
   so an entry without one displays as a bare "EVENT" row with no confidence,
   action or root cause — precisely the fields the compliance copy promises.

2. It is genuinely append-only. GET/append/SETEX is a read-modify-write, and the
   agent and executor run it against the same key from separate processes, so
   two concurrent writes lose one entry. RPUSH is atomic and cannot.

There is also a backward-compatibility obligation: keys written in the old
JSON-blob format still have to be readable, since a Redis holding real audit
history should not appear empty after a deploy.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from redis.exceptions import ResponseError  # noqa: E402

from agent.audit import EVENT_TYPES, AuditLogger, read_audit  # noqa: E402

# Event types the dashboard knows how to render, mirroring EVENT_STYLES in
# ui/src/components/AuditTimeline.tsx. Anything the backend emits outside this
# set reaches the operator as an unlabelled row with none of its detail.
UI_KNOWN_EVENT_TYPES = {
    "reasoning_complete",
    "action_executed",
    "approval_decision",
}


class FakeRedis:
    """
    A minimal stateful stand-in for Redis covering the commands the audit log
    uses.

    Statefulness matters: a plain AsyncMock returns None from every read, so
    each write starts from nothing and the log appears to hold one entry no
    matter how many were written — hiding the very behaviour under test.

    The string commands (get/setex) model the legacy JSON-blob format, and
    lrange raises WRONGTYPE against a string key exactly as Redis does, so the
    backward-compatible read path is exercised for real.

    get() reads before yielding because a real GET returns the value as of the
    moment it ran; that ordering is what lets two coroutines awaited together
    reproduce a genuine lost update rather than a staged one.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.expirations: dict[str, int] = {}

    # ── string commands (legacy format) ──
    async def get(self, key: str):
        value = self.store.get(key)
        await asyncio.sleep(0)
        return value

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        return True

    # ── list commands (current format) ──
    async def rpush(self, key: str, *values: str):
        if key in self.store:
            raise ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")
        await asyncio.sleep(0)
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    async def lrange(self, key: str, start: int, end: int):
        if key in self.store:
            raise ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    async def expire(self, key: str, ttl: int):
        self.expirations[key] = ttl
        return True


@pytest.fixture
def redis():
    return FakeRedis()


def written_entries(redis, incident_id: str = "inc-1") -> list[dict]:
    raw = redis.lists.get(f"audit:{incident_id}")
    assert raw is not None, "nothing was persisted"
    return [json.loads(r) for r in raw]


def _reasoning_result() -> dict:
    return {
        "status": "in_triage",
        "incident_type": "crash_loop",
        "probable_root_cause": "Missing env var.",
        "confidence_score": 0.94,
        "recommended_action": "rollout_restart",
        "requires_approval": True,
        "supporting_evidence": ["Log: FATAL missing env var"],
    }


# ── Every entry must be renderable ────────────────────────────────────────────


class TestEventTypeIsAlwaysPresent:
    async def test_reasoning_entry_has_event_type(self, redis):
        await AuditLogger(redis).record("inc-1", _reasoning_result())

        entry = written_entries(redis)[0]
        assert entry.get("event_type") == "reasoning_complete", (
            "the dashboard cannot render confidence, action or root cause "
            "without an event_type it recognises"
        )

    async def test_action_entry_has_event_type(self, redis):
        await AuditLogger(redis).record_action(
            "inc-1",
            action_type="rollout_restart",
            target="staging/payments-api",
            params={},
            success=True,
            result="Rollout restart triggered",
        )

        assert written_entries(redis)[0]["event_type"] == "action_executed"

    async def test_approval_entry_has_event_type(self, redis):
        await AuditLogger(redis).record_approval(
            "inc-1", approved=True, approver="operator", action_type="scale_up"
        )

        assert written_entries(redis)[0]["event_type"] == "approval_decision"

    async def test_every_emitted_event_type_is_known_to_the_ui(self, redis):
        logger = AuditLogger(redis)
        await logger.record("inc-1", _reasoning_result())
        await logger.record_approval(
            "inc-1", approved=True, approver="operator", action_type="scale_up"
        )
        await logger.record_action(
            "inc-1",
            action_type="scale_up",
            target="orders/order-service",
            params={},
            success=True,
            result="Scaled to 7",
        )

        emitted = {e.get("event_type") for e in written_entries(redis)}
        assert emitted <= UI_KNOWN_EVENT_TYPES, (
            f"backend emits {emitted - UI_KNOWN_EVENT_TYPES} which the "
            "dashboard has no rendering for"
        )
        assert emitted <= EVENT_TYPES, "backend disagrees with its own constant"


# ── The trail must record what the compliance copy claims ─────────────────────


class TestReasoningEntryContent:
    async def test_records_the_decision_inputs(self, redis):
        await AuditLogger(redis).record("inc-1", _reasoning_result())

        entry = written_entries(redis)[0]
        assert entry["confidence_score"] == 0.94
        assert entry["recommended_action"] == "rollout_restart"
        assert entry["incident_id"] == "inc-1"
        assert entry["supporting_evidence"] == ["Log: FATAL missing env var"]
        assert "ts" in entry


# ── Append-only means append-only ─────────────────────────────────────────────


class TestAppendOnly:
    async def test_entries_accumulate_when_written_sequentially(self, redis):
        logger = AuditLogger(redis)

        await logger.record("inc-1", _reasoning_result())
        await logger.record_approval(
            "inc-1", approved=True, approver="operator", action_type="rollout_restart"
        )

        assert len(written_entries(redis)) == 2

    async def test_concurrent_writers_do_not_lose_entries(self, redis):
        """
        Two writers reach the log at the same time — in production that is the
        agent recording its reasoning while the executor records an action, two
        separate processes against one key.

        Awaiting them together lets FakeRedis.get interleave them, so both read
        the same state and the second SETEX overwrites the first. An append-only
        log ends with two entries; a read-modify-write ends with one.
        """
        logger_a = AuditLogger(redis)
        logger_b = AuditLogger(redis)

        await asyncio.gather(
            logger_a.record("inc-1", _reasoning_result()),
            logger_b.record_approval(
                "inc-1",
                approved=True,
                approver="operator",
                action_type="rollout_restart",
            ),
        )

        assert len(written_entries(redis)) == 2, (
            "one writer's entry was overwritten by the other"
        )

    async def test_ttl_is_refreshed_on_each_append(self, redis):
        """An incident still generating activity keeps its full history."""
        await AuditLogger(redis).record("inc-1", _reasoning_result())
        assert redis.expirations["audit:inc-1"] == 60 * 60 * 24 * 30


# ── Reading back what earlier versions wrote ──────────────────────────────────


class TestLegacyFormatCompatibility:
    async def test_reads_entries_written_as_a_json_blob(self, redis):
        """
        A Redis carrying audit history from before the list migration must not
        read as empty — an operator seeing a blank compliance record cannot tell
        "nothing happened" from "we changed the storage format".
        """
        legacy = [
            {"ts": "2026-07-25T10:00:00+00:00", "event_type": "action_executed"},
            {"ts": "2026-07-25T10:00:04+00:00", "event_type": "approval_decision"},
        ]
        redis.store["audit:inc-legacy"] = json.dumps(legacy)

        entries = await read_audit(redis, "inc-legacy")

        assert [e["event_type"] for e in entries] == [
            "action_executed",
            "approval_decision",
        ]

    async def test_reads_current_format(self, redis):
        await AuditLogger(redis).record("inc-1", _reasoning_result())

        entries = await read_audit(redis, "inc-1")

        assert len(entries) == 1
        assert entries[0]["event_type"] == "reasoning_complete"

    async def test_unknown_incident_reads_as_empty(self, redis):
        assert await read_audit(redis, "no-such-incident") == []
