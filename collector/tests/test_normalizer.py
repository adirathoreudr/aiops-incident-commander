# collector/tests/test_normalizer.py
"""
Unit tests for alert normalization and fingerprinting logic.
No real cluster or Loki connection needed.
"""

import pytest
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from collector.normalizer import normalize_alertmanager_payload, _infer_log_level, _parse_severity
from collector.schema import AlertLabel, Severity, IncidentContext


# ── normalize_alertmanager_payload ────────────────────────────────────────────

class TestNormalize:
    def test_basic_fields(self):
        raw = {
            "labels": {
                "alertname": "KubePodCrashLooping",
                "namespace": "payments",
                "severity": "critical",
                "pod": "payments-api-abc",
                "deployment": "payments-api",
                "app": "payments-api",
            }
        }
        alert = normalize_alertmanager_payload(raw)
        assert alert.alertname == "KubePodCrashLooping"
        assert alert.namespace == "payments"
        assert alert.severity == Severity.CRITICAL
        assert alert.pod == "payments-api-abc"
        assert alert.deployment == "payments-api"

    def test_missing_severity_defaults_warning(self):
        raw = {"labels": {"alertname": "SomeAlert", "namespace": "default"}}
        alert = normalize_alertmanager_payload(raw)
        assert alert.severity == Severity.WARNING

    def test_extra_labels_captured(self):
        raw = {
            "labels": {
                "alertname": "X",
                "namespace": "ns",
                "custom_label": "custom_value",
            }
        }
        alert = normalize_alertmanager_payload(raw)
        assert "custom_label" in alert.extra
        assert alert.extra["custom_label"] == "custom_value"

    def test_severity_mapping(self):
        cases = [
            ("critical", Severity.CRITICAL),
            ("high",     Severity.HIGH),
            ("warning",  Severity.WARNING),
            ("warn",     Severity.WARNING),
            ("info",     Severity.INFO),
            ("unknown",  Severity.WARNING),
        ]
        for raw_sev, expected in cases:
            assert _parse_severity(raw_sev) == expected


# ── log level inference ───────────────────────────────────────────────────────

class TestLogLevel:
    def test_explicit_level_label(self):
        assert _infer_log_level("any message", {"level": "error"}) == "error"

    def test_keyword_error(self):
        assert _infer_log_level("FATAL: startup failed", {}) == "error"
        assert _infer_log_level("java.lang.NullPointerException", {}) == "error"

    def test_keyword_warn(self):
        assert _infer_log_level("WARNING: high memory usage", {}) == "warn"

    def test_default_info(self):
        assert _infer_log_level("server started on port 8080", {}) == "info"


# ── IncidentContext ───────────────────────────────────────────────────────────

class TestIncidentContext:
    def test_to_prompt_context_contains_key_fields(self):
        inc = IncidentContext(
            title="Test incident",
            severity=Severity.HIGH,
            namespace="staging",
            service="my-service",
            deployment="my-service",
            alerts=[AlertLabel(
                alertname="TestAlert",
                namespace="staging",
                severity=Severity.HIGH,
                service="my-service",
            )],
        )
        ctx = inc.to_prompt_context()
        assert "INCIDENT ID" in ctx
        assert "Test incident" in ctx
        assert "staging" in ctx
        assert "my-service" in ctx
        assert "TestAlert" in ctx

    def test_fingerprint_not_set_by_default(self):
        inc = IncidentContext(
            title="X", severity=Severity.INFO, namespace="default"
        )
        assert inc.fingerprint is None

    def test_mark_updated_changes_timestamp(self):
        inc = IncidentContext(
            title="X", severity=Severity.INFO, namespace="default"
        )
        old_ts = inc.updated_at
        import time; time.sleep(0.01)
        inc.mark_updated()
        assert inc.updated_at > old_ts
