# executor/tests/test_policy.py
"""
Unit tests for the PolicyEngine — the most critical safety component.
Every allowed/blocked/threshold rule is tested explicitly.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from executor.policy import PolicyEngine


class TestPolicyEngine:
    def setup_method(self):
        self.policy = PolicyEngine()

    # ── Allowlist ─────────────────────────────────────────────────────────────

    def test_unknown_action_blocked(self):
        allowed, reason = self.policy.check("delete_namespace", "staging", "app", 0.9)
        assert not allowed
        assert "allowlist" in reason.lower()

    def test_exec_into_pod_blocked(self):
        allowed, reason = self.policy.check("exec_pod", "staging", "app", 0.99)
        assert not allowed

    def test_notify_only_always_allowed(self):
        allowed, _ = self.policy.check("notify_only", "production", "", 0.0)
        assert allowed

    def test_rollout_restart_allowed_staging(self):
        allowed, _ = self.policy.check("rollout_restart", "staging", "payments-api", 0.80)
        assert allowed

    # ── Blocked namespaces ────────────────────────────────────────────────────

    def test_kube_system_blocked(self):
        allowed, reason = self.policy.check("rollout_restart", "kube-system", "coredns", 0.99)
        assert not allowed
        assert "blocked" in reason.lower()

    def test_kube_public_blocked(self):
        allowed, _ = self.policy.check("scale_up", "kube-public", "app", 0.99)
        assert not allowed

    def test_cert_manager_blocked(self):
        allowed, _ = self.policy.check("rollout_restart", "cert-manager", "cert-manager", 0.99)
        assert not allowed

    # ── Always-approval actions ───────────────────────────────────────────────

    def test_scale_down_always_needs_approval(self):
        allowed, reason = self.policy.check("scale_down", "staging", "app", 0.99)
        assert not allowed
        assert "approval" in reason.lower()

    def test_argocd_rollback_always_needs_approval(self):
        allowed, reason = self.policy.check("argocd_rollback", "staging", "app", 0.99)
        assert not allowed
        assert "approval" in reason.lower()

    # ── Confidence thresholds ─────────────────────────────────────────────────

    def test_low_confidence_blocked_non_prod(self):
        allowed, reason = self.policy.check("rollout_restart", "staging", "app", 0.50)
        assert not allowed
        assert "confidence" in reason.lower()

    def test_exactly_at_threshold_allowed(self):
        allowed, _ = self.policy.check("rollout_restart", "staging", "app", 0.75)
        assert allowed

    def test_high_risk_namespace_needs_higher_confidence(self):
        # 0.85 passes for staging but not for prod (requires 0.90)
        allowed_staging, _ = self.policy.check("rollout_restart", "staging", "app", 0.85)
        allowed_prod,    _ = self.policy.check("rollout_restart", "production", "app", 0.85)
        assert allowed_staging
        assert not allowed_prod

    def test_high_risk_namespace_passes_with_sufficient_confidence(self):
        allowed, _ = self.policy.check("rollout_restart", "production", "app", 0.90)
        assert allowed

    # ── Scale bounds ──────────────────────────────────────────────────────────

    def test_scale_above_max_blocked(self):
        allowed, reason = self.policy.check("scale_up", "staging", "app", 0.80, replicas=25)
        assert not allowed
        assert "MAX_REPLICAS" in reason

    def test_scale_below_min_blocked(self):
        allowed, reason = self.policy.check("scale_down", "staging", "app", 0.99, replicas=0)
        # scale_down hits always-approve first, but test the bounds for scale_up
        allowed2, reason2 = self.policy.check("scale_up", "staging", "app", 0.80, replicas=0)
        assert not allowed2

    def test_scale_within_bounds_allowed(self):
        allowed, _ = self.policy.check("scale_up", "staging", "app", 0.80, replicas=5)
        assert allowed

    # ── Missing deployment name ───────────────────────────────────────────────

    def test_missing_deployment_blocked_for_mutating_action(self):
        allowed, reason = self.policy.check("rollout_restart", "staging", "", 0.80)
        assert not allowed
        assert "deployment" in reason.lower()

    # ── is_high_risk helper ───────────────────────────────────────────────────

    def test_is_high_risk_prod(self):
        assert self.policy.is_high_risk("production", "rollout_restart")

    def test_is_high_risk_rollback(self):
        assert self.policy.is_high_risk("staging", "argocd_rollback")

    def test_not_high_risk_staging_restart(self):
        assert not self.policy.is_high_risk("staging", "rollout_restart")
