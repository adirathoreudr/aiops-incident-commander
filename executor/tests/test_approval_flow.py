"""
Regression tests for the human-approval path.

executor/main.py re-runs the policy gate *after* a human has approved an action.
That is the right instinct — approval should not be a bypass for the namespace
allowlist — but it only works if the gate can distinguish two very different
verdicts:

    "this action is forbidden"          (blocked namespace, unknown action)
    "this action needs a human first"   (scale_down, argocd_rollback, low confidence)

Collapsed into one boolean they are indistinguishable, and an action that merely
needed a human stays refused after the human approves it — the incident
dead-ends as escalated and the approval button does nothing.

PolicyEngine.evaluate returns ALLOW / REQUIRE_APPROVAL / BLOCK so the two stay
apart. These tests fix both halves of the contract: what approval unlocks, and
what it must never unlock.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from executor.policy import ALWAYS_REQUIRE_APPROVAL, PolicyEngine  # noqa: E402


def decide(policy: PolicyEngine, *, approved: bool = False, **kwargs) -> str:
    """Verdict as a plain string: "allow", "require_approval" or "block"."""
    decision, _reason = policy.evaluate(approved=approved, **kwargs)
    return decision.value


# ── What approval must unlock ─────────────────────────────────────────────────


class TestApprovalUnlocksGatedActions:
    @pytest.mark.parametrize("action", sorted(ALWAYS_REQUIRE_APPROVAL))
    def test_approved_action_is_permitted(self, action):
        verdict = decide(
            PolicyEngine(),
            approved=True,
            action_type=action,
            namespace="staging",
            deployment="order-service",
            confidence=0.95,
        )

        assert verdict == "allow", (
            f"a human approved {action!r} and the executor still refuses it; "
            "the incident is escalated instead of remediated"
        )

    def test_approved_low_confidence_action_is_permitted(self):
        verdict = decide(
            PolicyEngine(),
            approved=True,
            action_type="rollout_restart",
            namespace="staging",
            deployment="payments-api",
            confidence=0.20,
        )

        assert verdict == "allow"


# ── What approval must NOT unlock ─────────────────────────────────────────────


class TestApprovalIsNotAnOverride:
    """
    Approval means "a human vouched for this action", not "ignore the rules".
    A blocked namespace or an action outside the allowlist stays refused no
    matter who clicks approve — otherwise the approval button becomes a way to
    talk the platform into anything.
    """

    def test_blocked_namespace_stays_blocked_when_approved(self):
        verdict = decide(
            PolicyEngine(),
            approved=True,
            action_type="rollout_restart",
            namespace="kube-system",
            deployment="coredns",
            confidence=1.0,
        )

        assert verdict == "block"

    def test_unknown_action_stays_blocked_when_approved(self):
        verdict = decide(
            PolicyEngine(),
            approved=True,
            action_type="delete_namespace",
            namespace="staging",
            deployment="payments-api",
            confidence=1.0,
        )

        assert verdict == "block"


# ── Unapproved actions still need a human ─────────────────────────────────────


class TestUnapprovedActionsRouteToApproval:
    @pytest.mark.parametrize("action", sorted(ALWAYS_REQUIRE_APPROVAL))
    def test_gated_action_awaits_approval_rather_than_being_blocked(self, action):
        verdict = decide(
            PolicyEngine(),
            approved=False,
            action_type=action,
            namespace="staging",
            deployment="order-service",
            confidence=0.95,
        )

        assert verdict == "require_approval", (
            "the operator should see an approval prompt; instead the incident "
            "is dead-ended as escalated"
        )

    def test_auto_executable_action_needs_no_approval(self):
        verdict = decide(
            PolicyEngine(),
            approved=False,
            action_type="rollout_restart",
            namespace="staging",
            deployment="payments-api",
            confidence=0.90,
        )

        assert verdict == "allow"
