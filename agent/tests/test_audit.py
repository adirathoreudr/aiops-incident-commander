"""
Regression tests for agent/audit.py::AuditLogger.

Two things matter about the audit trail, and neither is currently guaranteed.

1. Every entry needs an ``event_type``. The dashboard switches on it
   (ui/src/components/AuditTimeline.tsx, EVENT_STYLES) to decide what to render.
   AuditLogger.record — the entry describing the AI's reasoning, which is the
   whole point of the audit tab — omits it, so it falls through to the default
   style and displays as a bare "EVENT" row with no confidence, action or root
   cause. The compliance copy on the audit page promises exactly those fields.

2. It has to actually be append-only. record() does GET -> append -> SETEX,
   which is a full overwrite, and the executor runs the same read-modify-write
   against the same key from a different process. Two concurrent writes lose
   one entry. Phase 2 replaces this with RPUSH.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.audit import AuditLogger  # noqa: E402

# Event types the dashboard knows how to render. Kept in sync by hand with
# EVENT_STYLES in ui/src/components/AuditTimeline.tsx — anything the backend
# emits that is not in this set renders as an unlabelled row.
UI_KNOWN_EVENT_TYPES = {
    "reasoning_complete",
    "action_executed",
    "approval_decision",
}


class FakeRedis:
    """
    A minimal stateful stand-in for Redis.

    Statefulness matters here: a plain AsyncMock returns None from every get(),
    so each write starts from an empty list and the log appears to hold exactly
    one entry no matter how many were written. That hides the very behaviour
    these tests exist to check.

    get() yields control before returning so that two coroutines awaited
    concurrently interleave the way two processes do — which is what makes the
    lost-update test below a real race rather than a staged one.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        # Read first, then yield. A real GET returns the value as it stood when
        # the command ran; whatever another writer does afterwards does not
        # retroactively change what this caller was handed. Yielding before the
        # read would let the second coroutine observe the first one's write and
        # hide the lost update entirely.
        value = self.store.get(key)
        await asyncio.sleep(0)
        return value

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        return True


@pytest.fixture
def redis():
    return FakeRedis()


def written_entries(redis, incident_id: str = "inc-1") -> list[dict]:
    raw = redis.store.get(f"audit:{incident_id}")
    assert raw is not None, "nothing was persisted"
    return json.loads(raw)


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
    @pytest.mark.xfail(
        strict=True,
        reason="Phase 2: AuditLogger.record omits event_type, so reasoning "
        "entries render as blank 'EVENT' rows with none of their detail.",
    )
    async def test_reasoning_entry_has_event_type(self, redis):
        await AuditLogger(redis).record("inc-1", _reasoning_result())

        entry = written_entries(redis)[0]
        assert entry.get("event_type") == "reasoning_complete", (
            "the dashboard cannot render confidence, action or root cause "
            "without an event_type it recognises"
        )

    async def test_action_entry_has_event_type(self, redis):
        """Contrast: record_action does set it, which is why actions render."""
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

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 2: see test_reasoning_entry_has_event_type.",
    )
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

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 2: GET/append/SETEX is a read-modify-write, and the "
        "executor runs the same cycle against the same key from another "
        "process. Concurrent writes silently drop an entry.",
    )
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
