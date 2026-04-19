# collector/tests/test_integration.py
"""
Integration tests for the collector FastAPI app.
Uses httpx TestClient — no real Redis, Loki, or K8s required.
Patches are applied at the module level to prevent actual I/O.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Patch Redis before importing app ─────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Create a TestClient with all external deps mocked."""
    mock_redis = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.lpush = AsyncMock(return_value=1)

    async def fake_from_url(*a, **kw):
        return mock_redis

    with patch("redis.asyncio.from_url", side_effect=fake_from_url):
        # Import app AFTER patching
        from collector.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── Health check ──────────────────────────────────────────────────────────────

class TestHealth:
    def test_healthz_returns_ok(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["service"] == "collector"

    def test_metrics_endpoint_exists(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers["content-type"]


# ── Alertmanager webhook ──────────────────────────────────────────────────────

class TestAlertmanagerWebhook:
    def _payload(self, alertname="TestAlert", severity="critical", namespace="staging"):
        return {
            "version": "4",
            "status": "firing",
            "alerts": [{
                "status": "firing",
                "labels": {
                    "alertname": alertname,
                    "namespace": namespace,
                    "severity": severity,
                    "deployment": "test-deploy",
                    "app": "test-app",
                    "service": "test-app",
                },
                "annotations": {"summary": "Test alert"},
                "startsAt": "2026-04-19T10:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
            }]
        }

    def test_webhook_returns_accepted(self, client):
        r = client.post(
            "/webhook/alertmanager",
            json=self._payload(),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_webhook_empty_alerts_accepted(self, client):
        r = client.post("/webhook/alertmanager", json={"alerts": []})
        assert r.status_code == 200

    def test_webhook_malformed_json_handled(self, client):
        # FastAPI should return 422 for invalid body, not 500
        r = client.post(
            "/webhook/alertmanager",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (200, 422)


# ── Simulate endpoint ─────────────────────────────────────────────────────────

class TestSimulate:
    def test_simulate_creates_incident(self, client):
        r = client.post("/webhook/simulate", json={
            "title": "Test CrashLoop",
            "alertname": "KubePodCrashLooping",
            "severity": "critical",
            "namespace": "staging",
            "service": "payments-api",
            "deployment": "payments-api",
        })
        assert r.status_code == 200
        body = r.json()
        assert "incident_id" in body
        assert body["status"] == "enqueued"
        assert body["incident_id"].startswith("inc-") or len(body["incident_id"]) > 0

    def test_simulate_all_severities(self, client):
        for sev in ["critical", "high", "warning", "info"]:
            r = client.post("/webhook/simulate", json={
                "title": f"{sev} incident",
                "severity": sev,
                "namespace": "test",
            })
            assert r.status_code == 200, f"Failed for severity={sev}"

    def test_simulate_minimal_payload(self, client):
        r = client.post("/webhook/simulate", json={})
        assert r.status_code == 200

    def test_simulate_returns_uuid_incident_id(self, client):
        import re
        r = client.post("/webhook/simulate", json={"title": "X", "severity": "info", "namespace": "ns"})
        body = r.json()
        assert re.match(r"[0-9a-f\-]{36}", body["incident_id"])


# ── Incidents list ────────────────────────────────────────────────────────────

class TestIncidentsList:
    def test_incidents_returns_list(self, client):
        r = client.get("/incidents")
        assert r.status_code == 200
        body = r.json()
        assert "incidents" in body
        assert "count" in body
        assert isinstance(body["incidents"], list)

    def test_incidents_404_for_unknown(self, client):
        r = client.get("/incidents/nonexistent-id-xyz")
        assert r.status_code == 404
