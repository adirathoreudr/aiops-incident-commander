# collector/tests/test_integration.py
"""
Integration tests for the collector FastAPI app.
Uses httpx TestClient — no real Redis, Loki, or K8s required.
Patches are applied at the module level to prevent actual I/O.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

# The collector's write paths require a bearer token. These tests exercise the
# real app, so they configure one and send it — see TestWriteEndpointsRequireAuth
# for the unauthenticated cases.
TEST_TOKEN = "integration-test-token"
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}

# ── Patch Redis before importing app ─────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """Create a TestClient with all external deps mocked."""
    os.environ["COLLECTOR_API_TOKEN"] = TEST_TOKEN
    import collector.auth as auth_module

    importlib.reload(auth_module)

    mock_redis = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.lpush = AsyncMock(return_value=1)
    # Incident ordering is served from a sorted set rather than a keyspace scan.
    mock_redis.zadd = AsyncMock(return_value=1)
    mock_redis.zrem = AsyncMock(return_value=1)
    mock_redis.zrevrange = AsyncMock(return_value=[])

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
            "alerts": [
                {
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
                }
            ],
        }

    def test_webhook_returns_accepted(self, client):
        r = client.post(
            "/webhook/alertmanager",
            json=self._payload(),
            headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_webhook_empty_alerts_accepted(self, client):
        r = client.post("/webhook/alertmanager", json={"alerts": []}, headers=AUTH)
        assert r.status_code == 200

    def test_webhook_malformed_json_handled(self, client):
        # FastAPI should return 422 for invalid body, not 500
        r = client.post(
            "/webhook/alertmanager",
            content="not-json",
            headers={"Content-Type": "application/json", **AUTH},
        )
        assert r.status_code in (200, 422)


# ── Simulate endpoint ─────────────────────────────────────────────────────────


class TestSimulate:
    def test_simulate_creates_incident(self, client):
        r = client.post(
            "/webhook/simulate",
            headers=AUTH,
            json={
                "title": "Test CrashLoop",
                "alertname": "KubePodCrashLooping",
                "severity": "critical",
                "namespace": "staging",
                "service": "payments-api",
                "deployment": "payments-api",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert "incident_id" in body
        assert body["status"] == "enqueued"
        assert body["incident_id"].startswith("inc-") or len(body["incident_id"]) > 0

    def test_simulate_all_severities(self, client):
        for sev in ["critical", "high", "warning", "info"]:
            r = client.post(
                "/webhook/simulate",
                headers=AUTH,
                json={
                    "title": f"{sev} incident",
                    "severity": sev,
                    "namespace": "test",
                },
            )
            assert r.status_code == 200, f"Failed for severity={sev}"

    def test_simulate_minimal_payload(self, client):
        r = client.post("/webhook/simulate", json={}, headers=AUTH)
        assert r.status_code == 200

    def test_simulate_returns_uuid_incident_id(self, client):
        import re

        r = client.post(
            "/webhook/simulate",
            headers=AUTH,
            json={"title": "X", "severity": "info", "namespace": "ns"},
        )
        body = r.json()
        assert re.match(r"[0-9a-f\-]{36}", body["incident_id"])


# ── Incidents list ────────────────────────────────────────────────────────────


class TestIncidentsList:
    def test_incidents_returns_list(self, client):
        r = client.get("/incidents", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert "incidents" in body
        assert "count" in body
        assert isinstance(body["incidents"], list)

    def test_incidents_404_for_unknown(self, client):
        r = client.get("/incidents/nonexistent-id-xyz", headers=AUTH)
        assert r.status_code == 404

    def test_incidents_served_in_index_order(self, client):
        """
        Order comes from the sorted set, newest first. Scanning incident:* and
        sorting the keys would order by UUID — which looks like it works and is
        actually arbitrary.
        """
        from collector import main as collector_main

        stored = {
            "incident:newer": '{"incident_id": "newer"}',
            "incident:older": '{"incident_id": "older"}',
        }
        collector_main.redis_client.zrevrange = AsyncMock(
            return_value=["newer", "older"]
        )
        collector_main.redis_client.get = AsyncMock(
            side_effect=lambda key: stored.get(key)
        )

        r = client.get("/incidents", headers=AUTH)

        assert [i["incident_id"] for i in r.json()["incidents"]] == ["newer", "older"]

    def test_expired_incidents_are_pruned_from_the_index(self, client):
        """
        Incidents expire on a TTL but the index entry does not, so a stale ID
        would otherwise accumulate forever and shrink the effective page size.
        """
        from collector import main as collector_main

        collector_main.redis_client.zrevrange = AsyncMock(
            return_value=["expired", "live"]
        )
        collector_main.redis_client.get = AsyncMock(
            side_effect=lambda key: (
                '{"incident_id": "live"}' if key == "incident:live" else None
            )
        )
        collector_main.redis_client.zrem = AsyncMock(return_value=1)

        r = client.get("/incidents", headers=AUTH)

        assert [i["incident_id"] for i in r.json()["incidents"]] == ["live"]
        collector_main.redis_client.zrem.assert_awaited_once_with(
            collector_main.INCIDENT_INDEX_KEY, "expired"
        )


# ── Auth on the real app ──────────────────────────────────────────────────────


class TestWriteEndpointsRequireAuth:
    """
    The unit tests in test_auth.py cover the dependency in isolation; these
    confirm it is actually wired onto the endpoints that matter on the real app.
    """

    def test_simulate_rejects_missing_token(self, client):
        r = client.post("/webhook/simulate", json={"title": "unauthorised"})
        assert r.status_code == 401

    def test_simulate_rejects_wrong_token(self, client):
        r = client.post(
            "/webhook/simulate",
            json={"title": "unauthorised"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401

    def test_alertmanager_rejects_wrong_token_once_configured(self, client):
        r = client.post(
            "/webhook/alertmanager",
            json={"alerts": []},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401

    def test_incident_reads_require_the_token_once_configured(self):
        """
        Incident bodies carry captured log lines and root-cause text. Guarding
        the executor's audit reads while leaving these open would protect
        nothing — the same content is in both.
        """
        assert client_unauthenticated_get("/incidents") == 401
        assert client_unauthenticated_get("/incidents/some-id") == 401

    def test_probe_endpoints_stay_open(self, client):
        """
        Kubernetes liveness probes and Prometheus scrapes carry no credentials,
        so these must never require one.
        """
        assert client.get("/healthz").status_code == 200
        assert client.get("/metrics").status_code == 200


def client_unauthenticated_get(path: str) -> int:
    """Status code for an unauthenticated GET against the running test app."""
    from collector.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        return c.get(path).status_code
