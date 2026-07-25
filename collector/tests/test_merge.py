"""
Regression tests for the dedup merge path in collector/main.py::_merge.

When a second alert fingerprints to an existing incident, _merge revives the
stored JSON via ``IncidentContext(**json.loads(raw))``. By that point the agent
and executor may already have written their own fields onto the incident.
Pydantic v2 ignores keys it does not declare, so any field absent from the
schema is silently dropped on the way back out — the merge quietly deletes the
analysis and remediation history for an incident that is still active.

The schema is meant to be the single canonical object for the whole lifecycle
(collector creates, agent enriches, executor acts), so the fix is to declare the
downstream fields rather than to work around the merge.
"""

from __future__ import annotations

import json

import pytest

from collector.schema import IncidentContext

# Fields written by the agent (reasoner) and executor after the collector has
# already persisted the incident. Each must survive a schema round-trip.
DOWNSTREAM_FIELDS = [
    "recommended_action_params",
    "last_action",
    "approved_by",
    "approved_at",
    "rejected_by",
    "policy_block_reason",
    "raw_llm_response",
]


def _enriched_incident() -> dict:
    """An incident as it looks *after* the agent and executor have touched it."""
    return {
        "title": "CrashLoopBackOff in payments/payments-api",
        "severity": "critical",
        "namespace": "payments",
        "service": "payments-api",
        "deployment": "payments-api",
        # ── collector-owned ──
        "fingerprint": "abc123def456",
        "grouped_alert_count": 3,
        # ── agent-owned ──
        "incident_type": "crash_loop",
        "probable_root_cause": "Missing STRIPE_API_VERSION env var.",
        "confidence_score": 0.94,
        "recommended_action": "scale_up",
        "recommended_action_params": {
            "deployment": "payments-api",
            "namespace": "payments",
            "replicas": 7,
        },
        "raw_llm_response": '{"incident_type": "crash_loop"}',
        # ── executor-owned ──
        "approved_by": "operator@example.com",
        "approved_at": "2026-07-25T10:00:00+00:00",
        "last_action": {
            "type": "scale_up",
            "result": "Scaled payments/payments-api to 7 replicas",
            "success": True,
            "ts": "2026-07-25T10:00:04+00:00",
        },
    }


class TestSchemaPreservesLifecycleFields:
    def test_collector_owned_fields_survive(self):
        """Sanity check: the fields the schema already declares round-trip fine."""
        revived = IncidentContext(**_enriched_incident())
        dumped = json.loads(revived.model_dump_json())

        assert dumped["probable_root_cause"] == "Missing STRIPE_API_VERSION env var."
        assert dumped["confidence_score"] == 0.94
        assert dumped["grouped_alert_count"] == 3

    @pytest.mark.parametrize("field", DOWNSTREAM_FIELDS)
    def test_downstream_field_survives_merge(self, field):
        revived = IncidentContext(**_enriched_incident())
        dumped = json.loads(revived.model_dump_json())

        assert field in dumped, (
            f"{field!r} was silently discarded by IncidentContext; "
            "a dedup merge on an active incident would erase it"
        )

    def test_replicas_survive_so_executor_can_scale(self):
        """
        The most damaging instance of the drop: the executor reads replicas from
        recommended_action_params. If a merge happens between reasoning and
        execution, the scale action loses its target and fails.
        """
        revived = IncidentContext(**_enriched_incident())
        dumped = json.loads(revived.model_dump_json())

        assert dumped["recommended_action_params"]["replicas"] == 7
