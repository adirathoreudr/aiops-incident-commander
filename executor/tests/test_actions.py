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
from executor.policy import MAX_REPLICAS  # noqa: E402


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

    async def test_missing_replicas_derives_a_target(self, dispatcher, apps_api):
        """
        scale_up with no explicit replica count is the common case — the model
        frequently omits it — so it has to resolve to something rather than
        failing.
        """
        deployment = MagicMock()
        deployment.spec.replicas = 4
        apps_api.read_namespaced_deployment.return_value = deployment

        result = await dispatcher.execute(
            action_type="scale_up",
            namespace="orders",
            deployment="order-service",
            replicas=None,
        )

        assert result["success"] is True
        kwargs = apps_api.patch_namespaced_deployment_scale.call_args.kwargs
        assert kwargs["body"] == {"spec": {"replicas": 6}}  # ceil(4 * 1.5)

    async def test_derived_target_respects_the_policy_ceiling(
        self, dispatcher, apps_api
    ):
        deployment = MagicMock()
        deployment.spec.replicas = 19
        apps_api.read_namespaced_deployment.return_value = deployment

        await dispatcher.execute(
            action_type="scale_up",
            namespace="orders",
            deployment="order-service",
            replicas=None,
        )

        kwargs = apps_api.patch_namespaced_deployment_scale.call_args.kwargs
        assert kwargs["body"]["spec"]["replicas"] == MAX_REPLICAS

    async def test_scale_down_refuses_to_guess(self, dispatcher, apps_api):
        """
        Deriving a scale_up target is a safe bet; guessing how far to shed
        capacity during an incident is how a slowdown becomes an outage.
        """
        result = await dispatcher.execute(
            action_type="scale_down",
            namespace="orders",
            deployment="order-service",
            replicas=None,
        )

        assert result["success"] is False
        apps_api.patch_namespaced_deployment_scale.assert_not_called()

    async def test_unreadable_deployment_fails_cleanly(self, dispatcher, apps_api):
        apps_api.read_namespaced_deployment.side_effect = RuntimeError("no such thing")

        result = await dispatcher.execute(
            action_type="scale_up",
            namespace="orders",
            deployment="order-service",
            replicas=None,
        )

        assert result["success"] is False
        apps_api.patch_namespaced_deployment_scale.assert_not_called()


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


class TestBlockingCallsAreOffloaded:
    """
    The kubernetes client is synchronous. Called straight from a coroutine it
    holds the event loop for the whole round trip, which stalls everything else
    the executor is serving — /healthz included. With a liveness probe at
    periodSeconds 30 and failureThreshold 3, an unresponsive API server gets the
    pod killed by the kubelet in the middle of a remediation.

    These tests assert the blocking work happens off the loop, by checking that
    the event loop stays responsive while an action is in flight.
    """

    async def test_event_loop_stays_responsive_during_a_slow_scale(
        self, dispatcher, apps_api
    ):
        import asyncio
        import time

        def slow_patch(*a, **kw):
            time.sleep(0.4)
            return None

        apps_api.patch_namespaced_deployment_scale.side_effect = slow_patch

        action = asyncio.create_task(
            dispatcher.execute(
                action_type="scale_up",
                namespace="orders",
                deployment="order-service",
                replicas=5,
            )
        )

        # Stand in for /healthz: a trivial coroutine that must not be delayed.
        t0 = time.perf_counter()
        ticks = 0
        while not action.done():
            await asyncio.sleep(0.01)
            ticks += 1
        elapsed = time.perf_counter() - t0

        await action
        assert elapsed >= 0.4, "sanity: the action really did take time"
        assert ticks > 5, (
            f"the loop only got {ticks} chance(s) to run during a 0.4s call — the "
            "blocking work is still on the event loop"
        )

    async def test_rollout_restart_is_also_offloaded(self, dispatcher, apps_api):
        import asyncio
        import time

        apps_api.patch_namespaced_deployment.side_effect = lambda *a, **kw: time.sleep(0.3)

        task = asyncio.create_task(
            dispatcher.execute(
                action_type="rollout_restart",
                namespace="staging",
                deployment="payments-api",
            )
        )
        ticks = 0
        while not task.done():
            await asyncio.sleep(0.01)
            ticks += 1
        await task

        assert ticks > 5, "rollout_restart is still blocking the event loop"
