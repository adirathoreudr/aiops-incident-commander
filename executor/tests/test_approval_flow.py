"""
Regression tests for the human-approval path.

executor/main.py re-runs the policy gate *after* a human has approved an action.
That is the right instinct — approval should not be a bypass for the namespace
allowlist — but PolicyEngine.check() currently returns a single boolean that
conflates two very different verdicts:

    "this action is forbidden"          (blocked namespace, unknown action)
    "this action needs a human first"   (scale_down, argocd_rollback, low confidence)

Because both come back as ``False``, an action that merely needed a human is
still refused *after* the human approves it. The approval button cannot work for
scale_down or argocd_rollback: the incident goes straight to `escalated`.

The fix (Phase 1b) is a three-valued decision — ALLOW / REQUIRE_APPROVAL / BLOCK
— so the worker can tell "a human already handled this" apart from "never".
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from executor.policy import ALWAYS_REQUIRE_APPROVAL, PolicyEngine  # noqa: E402


def decide(policy: PolicyEngine, *, approved: bool = False, **kwargs) -> str:
    """
    Ask the policy engine for a verdict as one of "allow" / "require_approval" /
    "block".

    Phase 1b introduces PolicyEngine.evaluate() with exactly these semantics.
    Until it lands we fall back to check(), which cannot express
    "require_approval" — so it reports "block" and the xfail tests below fail as
    intended. Once evaluate() exists this shim starts returning the real verdict
    and the xfails flip to XPASS, which (being strict) fails the suite and
    prompts removing the markers.
    """
    if hasattr(policy, "evaluate"):
        decision, _reason = policy.evaluate(approved=approved, **kwargs)
        return str(getattr(decision, "value", decision))

    allowed, _reason = policy.check(**kwargs)
    return "allow" if allowed else "block"


# ── What approval must unlock ─────────────────────────────────────────────────


class TestApprovalUnlocksGatedActions:
    @pytest.mark.xfail(
        strict=True,
        reason="Phase 1b: the post-approval policy gate cannot distinguish "
        "'needed a human' from 'forbidden', so approving scale_down is a no-op.",
    )
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

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 1b: low-confidence incidents are blocked outright rather "
        "than routed to the approval queue, so approving them does nothing.",
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
    @pytest.mark.xfail(
        strict=True,
        reason="Phase 1b: check() collapses require_approval into block, so the "
        "worker marks these 'escalated' instead of queueing them for a human.",
    )
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
