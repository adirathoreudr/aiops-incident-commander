"""
Tests for collector authentication.

The collector never touches the cluster, which makes it look read-only. It is
not: /webhook/simulate puts an incident straight onto the agent queue, and a
confident incident in a permitted namespace is auto-executed with no human in
the loop. Unauthenticated, it is a remote "restart this deployment" button
wearing a test-fixture label.

The two write paths deliberately behave differently when no token is configured,
and that asymmetry is the thing most worth pinning down:

  /webhook/simulate     fails closed — an operator tool nobody needs by default
  /webhook/alertmanager stays open   — requiring a token unconditionally would
                                       stop real alert ingestion on upgrade, and
                                       a platform that silently sees no alerts is
                                       worse than one with an open ingest path
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TOKEN = "collector-token-value"


def _client(token: str | None):
    if token is None:
        os.environ.pop("COLLECTOR_API_TOKEN", None)
    else:
        os.environ["COLLECTOR_API_TOKEN"] = token

    import collector.auth as auth_module

    importlib.reload(auth_module)

    app = FastAPI()

    @app.post("/simulate", dependencies=[Depends(auth_module.require_token)])
    async def simulate():
        return {"ok": True}

    @app.post(
        "/alertmanager",
        dependencies=[Depends(auth_module.require_token_if_configured)],
    )
    async def alertmanager():
        return {"ok": True}

    return TestClient(app)


@pytest.fixture(autouse=True)
def _restore_env():
    """
    Put both the environment and the module back afterwards.

    Reloading collector.auth mutates the live module dict, which the running
    app's dependency closes over — so without the reload on the way out these
    tests would leave a token configured and every other test in the session
    would start getting 401s.
    """
    original = os.environ.get("COLLECTOR_API_TOKEN")
    yield
    if original is None:
        os.environ.pop("COLLECTOR_API_TOKEN", None)
    else:
        os.environ["COLLECTOR_API_TOKEN"] = original

    import collector.auth as auth_module

    importlib.reload(auth_module)


class TestSimulateFailsClosed:
    def test_rejected_without_a_configured_token(self):
        assert _client(None).post("/simulate").status_code == 503

    def test_rejected_with_the_wrong_token(self):
        client = _client(TOKEN)
        r = client.post("/simulate", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401

    def test_accepted_with_the_right_token(self):
        client = _client(TOKEN)
        r = client.post("/simulate", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200


class TestAlertmanagerEnforcedOnlyWhenConfigured:
    def test_open_when_no_token_is_configured(self):
        """
        Deliberate: an unset token must not silently stop the platform receiving
        production alerts.
        """
        assert _client(None).post("/alertmanager").status_code == 200

    def test_required_once_a_token_is_configured(self):
        assert _client(TOKEN).post("/alertmanager").status_code == 401

    def test_accepted_with_the_right_token(self):
        client = _client(TOKEN)
        r = client.post("/alertmanager", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200
