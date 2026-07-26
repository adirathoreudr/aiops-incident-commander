"""
Tests for executor authentication and CORS.

/approve and /execute/manual are the two doors into the cluster. They had no
authentication at all and CORS was open to every origin, so anyone able to reach
the executor could restart or rescale a workload. The policy engine constrains
*what* may happen; nothing constrained *who* could ask.

The most important case here is the unconfigured one. If an absent token meant
"skip the checks", every deployment that forgot to set it would be exactly as
exposed as before, and silently so — the tests below fix that it fails closed.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TOKEN = "s3cret-token-value"


def _client(token: str | None):
    """
    Build a tiny app wired to the auth dependency.

    The module reads its token at import time, so it is reimported under the
    desired environment rather than patched — that also proves the variable is
    actually what governs the behaviour.
    """
    if token is None:
        os.environ.pop("EXECUTOR_API_TOKEN", None)
    else:
        os.environ["EXECUTOR_API_TOKEN"] = token

    import executor.auth as auth_module

    importlib.reload(auth_module)

    app = FastAPI()

    @app.post("/mutate", dependencies=[Depends(auth_module.require_token)])
    async def mutate():
        return {"ok": True}

    @app.get("/read", dependencies=[Depends(auth_module.require_token_if_configured)])
    async def read():
        return {"ok": True}

    return TestClient(app), auth_module


@pytest.fixture(autouse=True)
def _restore_env():
    """
    Put both the environment and the modules back afterwards.

    Reloading mutates the live module dict, which any running app's dependency
    closes over — so without the reload on the way out these tests would leave a
    token configured and other tests in the session would start seeing 401s.
    """
    original = os.environ.get("EXECUTOR_API_TOKEN")
    original_cors = os.environ.get("CORS_ALLOWED_ORIGINS")
    yield

    for name, value in (
        ("EXECUTOR_API_TOKEN", original),
        ("CORS_ALLOWED_ORIGINS", original_cors),
    ):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    import executor.auth as auth_module
    import executor.cors as cors_module

    importlib.reload(auth_module)
    importlib.reload(cors_module)


class TestTokenEnforcement:
    def test_correct_token_is_accepted(self):
        client, _ = _client(TOKEN)
        r = client.post("/mutate", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200

    def test_missing_header_is_rejected(self):
        client, _ = _client(TOKEN)
        r = client.post("/mutate")
        assert r.status_code == 401

    def test_wrong_token_is_rejected(self):
        client, _ = _client(TOKEN)
        r = client.post("/mutate", headers={"Authorization": "Bearer not-the-token"})
        assert r.status_code == 401

    def test_token_prefix_is_rejected(self):
        """A partial match must not pass — the comparison is on the whole value."""
        client, _ = _client(TOKEN)
        r = client.post("/mutate", headers={"Authorization": f"Bearer {TOKEN[:8]}"})
        assert r.status_code == 401

    def test_empty_bearer_is_rejected(self):
        client, _ = _client(TOKEN)
        r = client.post("/mutate", headers={"Authorization": "Bearer "})
        assert r.status_code == 401


class TestFailsClosedWhenUnconfigured:
    def test_unset_token_refuses_even_a_correct_looking_request(self):
        """
        The critical case. If an unset token meant "no checks", every deployment
        that forgot to configure one would keep the original hole — open to
        anyone who can reach the port, and quietly.
        """
        client, _ = _client(None)

        assert client.post("/mutate").status_code == 503
        assert (
            client.post("/mutate", headers={"Authorization": "Bearer anything"}).status_code
            == 503
        )

    def test_empty_string_token_also_fails_closed(self):
        client, _ = _client("")
        assert client.post("/mutate").status_code == 503

    def test_the_503_explains_what_to_do(self):
        client, _ = _client(None)
        assert "EXECUTOR_API_TOKEN" in client.post("/mutate").json()["detail"]


class TestReadGuardIsGraduated:
    """
    Reads cannot change the cluster, but audit entries and incident bodies carry
    root-cause text and captured log lines, so they are not public either. The
    guard therefore engages once a token exists rather than failing closed —
    breaking the dashboard for every unconfigured deployment would push people
    toward disabling authentication altogether.
    """

    def test_open_when_no_token_is_configured(self):
        client, _ = _client(None)
        assert client.get("/read").status_code == 200

    def test_required_once_a_token_is_configured(self):
        client, _ = _client(TOKEN)
        assert client.get("/read").status_code == 401

    def test_accepted_with_the_right_token(self):
        client, _ = _client(TOKEN)
        r = client.get("/read", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200

    def test_reads_never_return_503(self):
        """
        Unlike the mutating endpoints, an unconfigured read path stays usable —
        503 here would mean the dashboard cannot render at all.
        """
        client, _ = _client(None)
        assert client.get("/read").status_code != 503


class TestCorsPolicy:
    def _origins(self, value: str | None):
        if value is None:
            os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        else:
            os.environ["CORS_ALLOWED_ORIGINS"] = value
        import executor.cors as cors_module

        importlib.reload(cors_module)
        return cors_module.allowed_origins()

    def test_defaults_to_the_local_dashboard_not_wildcard(self):
        origins = self._origins(None)
        assert "*" not in origins
        assert "http://localhost:3001" in origins

    def test_explicit_list_is_parsed(self):
        assert self._origins("https://a.example, https://b.example") == [
            "https://a.example",
            "https://b.example",
        ]

    def test_wildcard_is_honoured_but_must_be_asked_for(self):
        """
        A gateway in front of the service may legitimately own this decision, so
        '*' stays possible — it just must never be what you get by accident.
        """
        assert self._origins("*") == ["*"]
