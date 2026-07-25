"""
Regression tests for agent/reasoner.py::IncidentReasoner.reason.

The reasoner is the seam between the LLM's structured output and everything
downstream. Its merge step decides which parsed fields actually reach Redis, and
therefore which ones the executor can act on. A field the prompt asks for, the
parser returns, and the merge forgets is invisible until an action fails in
production — which is exactly what happens today with recommended_action_params.

These tests never touch the network: they bypass __init__ (which would build a
real ChatOpenAI/ChatAnthropic client and a FAISS-backed KnowledgeStore) and
inject a fake LLM whose response we control.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.reasoner import IncidentReasoner  # noqa: E402

# ── Test doubles ──────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Returns a canned response; records the messages it was called with."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return _FakeResponse(self._content)


class _ExplodingLLM:
    async def ainvoke(self, messages):
        raise RuntimeError("upstream LLM unavailable")


class _FakeKnowledge:
    def search_incidents(self, query, k=3):
        return []

    def search_runbooks(self, query, k=2):
        return []


def _reasoner(llm) -> IncidentReasoner:
    """Build a reasoner without running __init__ (no API keys, no network)."""
    r = object.__new__(IncidentReasoner)
    r.llm = llm
    r.knowledge = _FakeKnowledge()
    return r


def _llm_payload(**overrides) -> str:
    payload = {
        "incident_type": "high_latency",
        "probable_root_cause": "Traffic spike saturated the worker pool.",
        "confidence_score": 0.88,
        "supporting_evidence": ["RPS 420 -> 1340", "CPU at limit"],
        "recommended_action": "scale_up",
        "recommended_action_params": {
            "deployment": "order-service",
            "namespace": "orders",
            "replicas": 7,
        },
        "requires_approval": False,
        "approval_reason": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _incident() -> dict:
    return {
        "incident_id": "inc-test-1",
        "title": "High p95 latency — order-service",
        "severity": "high",
        "namespace": "orders",
        "service": "order-service",
        "deployment": "order-service",
        "alerts": [{"alertname": "HighResponseTime", "severity": "high"}],
        "logs": [],
        "rollout_events": [],
    }


# ── The bug this phase exists to pin down ─────────────────────────────────────


class TestActionParamsPropagation:
    @pytest.mark.xfail(
        strict=True,
        reason="Phase 1a: reason() omits recommended_action_params from its "
        "merge, so the executor never receives a replica target and every "
        "scale action fails with 'replicas parameter required'.",
    )
    async def test_action_params_reach_the_incident(self):
        result = await _reasoner(_FakeLLM(_llm_payload())).reason(_incident())

        assert "recommended_action_params" in result, (
            "the prompt asks for recommended_action_params and the parser "
            "returns them, but reason() drops them before persisting"
        )
        assert result["recommended_action_params"]["replicas"] == 7

    async def test_action_itself_is_propagated(self):
        """Contrast: the action name *is* merged, which is why this looks fine."""
        result = await _reasoner(_FakeLLM(_llm_payload())).reason(_incident())
        assert result["recommended_action"] == "scale_up"


# ── Behaviour that is already correct and must stay that way ──────────────────


class TestPolicyOverrides:
    async def test_low_confidence_forces_approval(self):
        result = await _reasoner(
            _FakeLLM(_llm_payload(confidence_score=0.30, requires_approval=False))
        ).reason(_incident())

        assert result["requires_approval"] is True
        assert result["status"] == "in_triage"

    async def test_critical_severity_forces_approval(self):
        incident = _incident()
        incident["severity"] = "critical"

        result = await _reasoner(
            _FakeLLM(_llm_payload(confidence_score=0.99, requires_approval=False))
        ).reason(incident)

        assert result["requires_approval"] is True

    async def test_model_cannot_downgrade_approval_requirement(self):
        """
        The LLM may only ever escalate to human review, never away from it.
        A prompt-injected log line saying "no approval needed" must not be able
        to talk the platform into touching a production namespace unattended.
        """
        incident = _incident()
        incident["namespace"] = "production"

        result = await _reasoner(
            _FakeLLM(_llm_payload(confidence_score=1.0, requires_approval=False))
        ).reason(incident)

        assert result["requires_approval"] is True

    async def test_high_confidence_staging_can_auto_execute(self):
        result = await _reasoner(
            _FakeLLM(_llm_payload(confidence_score=0.92, requires_approval=False))
        ).reason(_incident())

        assert result["requires_approval"] is False
        assert result["status"] == "remediating"


class TestFailureHandling:
    async def test_llm_failure_escalates_rather_than_crashing(self):
        result = await _reasoner(_ExplodingLLM()).reason(_incident())

        assert result["status"] == "escalated"
        assert result["requires_approval"] is True
        assert result["confidence_score"] == 0.0

    async def test_unparseable_response_falls_back_to_notify_only(self):
        result = await _reasoner(_FakeLLM("not json at all")).reason(_incident())

        assert result["recommended_action"] == "notify_only"
        assert result["requires_approval"] is True
        assert result["confidence_score"] == 0.0
