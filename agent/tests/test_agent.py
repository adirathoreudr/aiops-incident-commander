# agent/tests/test_agent.py
"""
Unit tests for agent prompt parsing and policy logic.
Does not call OpenAI API — all LLM calls are mocked.
"""

import pytest
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from agent.prompts.incident_prompt import parse_agent_response, build_human_prompt


# ── parse_agent_response ──────────────────────────────────────────────────────

class TestParseAgentResponse:
    def test_valid_json(self):
        payload = {
            "incident_type": "crash_loop",
            "probable_root_cause": "Missing env var STRIPE_KEY caused startup panic.",
            "confidence_score": 0.92,
            "supporting_evidence": ["Log: FATAL missing env var", "Rollout 90s before incident"],
            "recommended_action": "rollout_restart",
            "recommended_action_params": {"deployment": "payments-api", "namespace": "payments"},
            "requires_approval": False,
            "approval_reason": "",
        }
        result = parse_agent_response(json.dumps(payload))
        assert result["incident_type"] == "crash_loop"
        assert result["confidence_score"] == 0.92
        assert result["recommended_action"] == "rollout_restart"
        assert len(result["supporting_evidence"]) == 2

    def test_markdown_fenced_json(self):
        raw = "```json\n{\"incident_type\": \"oom_kill\", \"confidence_score\": 0.85, \"probable_root_cause\": \"OOM\", \"supporting_evidence\": [], \"recommended_action\": \"scale_up\", \"recommended_action_params\": {}, \"requires_approval\": false, \"approval_reason\": \"\"}\n```"
        result = parse_agent_response(raw)
        assert result["incident_type"] == "oom_kill"
        assert result["confidence_score"] == 0.85

    def test_invalid_json_returns_safe_defaults(self):
        result = parse_agent_response("this is not json at all")
        assert result["confidence_score"] == 0.0
        assert result["requires_approval"] is True
        assert result["recommended_action"] == "notify_only"
        assert result["incident_type"] == "unknown"

    def test_confidence_clamped_above_1(self):
        result = parse_agent_response('{"confidence_score": 1.5, "incident_type": "x", "probable_root_cause": "x", "supporting_evidence": [], "recommended_action": "notify_only", "recommended_action_params": {}, "requires_approval": false, "approval_reason": ""}')
        assert result["confidence_score"] == 1.0

    def test_confidence_clamped_below_0(self):
        result = parse_agent_response('{"confidence_score": -0.2, "incident_type": "x", "probable_root_cause": "x", "supporting_evidence": [], "recommended_action": "notify_only", "recommended_action_params": {}, "requires_approval": false, "approval_reason": ""}')
        assert result["confidence_score"] == 0.0


# ── build_human_prompt ────────────────────────────────────────────────────────

class TestBuildHumanPrompt:
    def _sample_incident(self):
        return {
            "incident_id": "test-123",
            "title": "CrashLoop in payments-api",
            "severity": "critical",
            "namespace": "payments",
            "service": "payments-api",
            "deployment": "payments-api",
            "pod": "payments-api-abc",
            "image_tag": "payments-api:v2.4.0",
            "alerts": [{"severity": "critical", "alertname": "KubePodCrashLooping", "namespace": "payments"}],
            "logs": [
                {"timestamp": "2026-04-19T10:00:00Z", "level": "fatal", "message": "FATAL: missing env var STRIPE_KEY"}
            ],
            "rollout_events": [
                {"deployment": "payments-api", "revision": 12, "image": "payments-api:v2.4.0", "status": "complete", "started_at": "2026-04-19T09:58:00Z"}
            ],
        }

    def test_contains_incident_id(self):
        prompt = build_human_prompt(self._sample_incident(), [], [])
        assert "test-123" in prompt

    def test_contains_alerts(self):
        prompt = build_human_prompt(self._sample_incident(), [], [])
        assert "KubePodCrashLooping" in prompt

    def test_contains_log_message(self):
        prompt = build_human_prompt(self._sample_incident(), [], [])
        assert "FATAL: missing env var" in prompt

    def test_contains_rollout_image(self):
        prompt = build_human_prompt(self._sample_incident(), [], [])
        assert "payments-api:v2.4.0" in prompt

    def test_similar_incidents_included(self):
        similar = [{"title": "Past CrashLoop", "probable_root_cause": "Bad config", "resolved_by": "rollout_restart"}]
        prompt = build_human_prompt(self._sample_incident(), similar, [])
        assert "Past CrashLoop" in prompt

    def test_runbooks_included(self):
        runbooks = [{"title": "CrashLoop Runbook", "summary": "Restart the pod", "action": "rollout_restart"}]
        prompt = build_human_prompt(self._sample_incident(), [], runbooks)
        assert "CrashLoop Runbook" in prompt
