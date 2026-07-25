"""
Regression tests for executor/actions.py::ActionDispatcher.

The dispatcher is the only code in the platform that mutates a live cluster, and
it has had no test coverage at all. These tests pin down two things: that each
action issues the Kubernetes call it claims to, and that a dispatcher which
cannot reach a cluster degrades to a failure result rather than raising — the
worker loop relies on ``execute`` never throwing.

The Kubernetes client is mocked throughout; nothing here talks to a cluster.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from executor.actions import ActionDispatcher  # noqa: E402


@pytest.fixture
def apps_api():
    """Patch AppsV1Api and hand back the mock instance the dispatcher will use."""
    instance = MagicMock()
    with patch("executor.actions.k8s_client.AppsV1Api", return_value=instance):
        yield instance


@pytest.fixture
def dispatcher():
    # _load_k8s() logs a warning and continues when no kubeconfig is present,
    # so construction is safe in CI.
    return ActionDispatcher()


# ── rollout_restart ───────────────────────────────────────────────────────────


class TestRolloutRestart:
    async def test_patches_restart_annotation(self, dispatcher, apps_api):
        result = await dispatcher.execute(
            action_type="rollout_restart",
            namespace="staging",
            deployment="payments-api",
        )

        assert result["success"] is True
        apps_api.patch_namespaced_deployment.assert_called_once()

        kwargs = apps_api.patch_namespaced_deployment.call_args.kwargs
        assert kwargs["name"] == "payments-api"
        assert kwargs["namespace"] == "staging"
        annotations = kwargs["body"]["spec"]["template"]["metadata"]["annotations"]
        assert "kubectl.kubernetes.io/restartedAt" in annotations

    async def test_api_failure_returns_result_instead_of_raising(
        self, dispatcher, apps_api
    ):
        apps_api.patch_namespaced_deployment.side_effect = RuntimeError("boom")

        result = await dispatcher.execute(
            action_type="rollout_restart",
            namespace="staging",
            deployment="payments-api",
        )

        assert result["success"] is False
        assert "error" in result["message"].lower()


# ── scale ─────────────────────────────────────────────────────────────────────


class TestScale:
    async def test_explicit_replicas_are_applied(self, dispatcher, apps_api):
        result = await dispatcher.execute(
            action_type="scale_up",
            namespace="orders",
            deployment="order-service",
            replicas=7,
        )

        assert result["success"] is True
        kwargs = apps_api.patch_namespaced_deployment_scale.call_args.kwargs
        assert kwargs["body"] == {"spec": {"replicas": 7}}

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 1d: with no replica count the dispatcher gives up, so a "
        "scale_up recommendation that omits replicas can never execute. It "
        "should derive a target from the deployment's current replica count.",
    )
    async def test_missing_replicas_derives_a_target(self, dispatcher, apps_api):
        apps_api.read_namespaced_deployment.return_value = MagicMock(
            spec_replicas=3, **{"spec.replicas": 3}
        )

        result = await dispatcher.execute(
            action_type="scale_up",
            namespace="orders",
            deployment="order-service",
            replicas=None,
        )

        assert result["success"] is True, (
            "scale_up with no explicit replica count is the common case — the "
            "LLM frequently omits it — and it currently always fails"
        )
        apps_api.patch_namespaced_deployment_scale.assert_called_once()


# ── notify_only and unknown actions ───────────────────────────────────────────


class TestNonMutatingActions:
    async def test_notify_only_touches_nothing(self, dispatcher, apps_api):
        result = await dispatcher.execute(
            action_type="notify_only",
            namespace="staging",
            deployment="payments-api",
        )

        assert result["success"] is True
        apps_api.patch_namespaced_deployment.assert_not_called()
        apps_api.patch_namespaced_deployment_scale.assert_not_called()

    async def test_unknown_action_is_refused_and_mutates_nothing(
        self, dispatcher, apps_api
    ):
        """
        Defence in depth: the policy engine should already have rejected this,
        but the dispatcher must not fall through to a mutating call if a new
        action type is ever added to the prompt without a policy entry.
        """
        result = await dispatcher.execute(
            action_type="delete_namespace",
            namespace="staging",
            deployment="payments-api",
        )

        assert result["success"] is False
        assert result["action"] == "unknown"
        apps_api.patch_namespaced_deployment.assert_not_called()
        apps_api.patch_namespaced_deployment_scale.assert_not_called()


# ── argocd_rollback ───────────────────────────────────────────────────────────


class TestArgoRollback:
    async def test_missing_token_is_reported_not_raised(self, dispatcher):
        with patch("executor.actions.ARGOCD_TOKEN", ""):
            result = await dispatcher.execute(
                action_type="argocd_rollback",
                namespace="staging",
                deployment="payments-api",
            )

        assert result["success"] is False
        assert "ARGOCD_TOKEN" in result["message"]
