"""
executor/policy.py
Policy engine: validates every action before execution.
Blocks anything not on the allowlist.
Enforces confidence thresholds and namespace restrictions.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("executor.policy")

# ── Policy config (override via env) ─────────────────────────────────────────

BLOCKED_NAMESPACES = set(
    os.getenv("BLOCKED_NAMESPACES", "kube-system,kube-public,cert-manager").split(",")
)
HIGH_RISK_NAMESPACES = set(
    os.getenv("HIGH_RISK_NAMESPACES", "production,prod").split(",")
)
MIN_CONFIDENCE_AUTO = float(os.getenv("MIN_CONFIDENCE_AUTO", "0.75"))
MIN_CONFIDENCE_HIGH_RISK = float(os.getenv("MIN_CONFIDENCE_HIGH_RISK", "0.90"))
MAX_REPLICAS = int(os.getenv("MAX_SCALE_REPLICAS", "20"))
MIN_REPLICAS = int(os.getenv("MIN_SCALE_REPLICAS", "1"))

# Explicitly allowed action types only — anything else is BLOCKED
ALLOWED_ACTIONS = {
    "rollout_restart",
    "scale_up",
    "scale_down",
    "argocd_rollback",
    "notify_only",
}

# Actions that always require human approval regardless of confidence
ALWAYS_REQUIRE_APPROVAL = {
    "scale_down",   # may reduce capacity in prod
    "argocd_rollback",  # state mutation — human must confirm
}


class PolicyEngine:
    """
    Stateless policy checker.
    Returns (allowed: bool, reason: str).
    """

    def check(
        self,
        action_type: str,
        namespace: str,
        deployment: str,
        confidence: float,
        replicas: int | None = None,
    ) -> tuple[bool, str]:

        # ── 1. Allowlist ──────────────────────────────────────────────────────
        if action_type not in ALLOWED_ACTIONS:
            msg = f"Action '{action_type}' not in approved action allowlist"
            log.warning("POLICY BLOCK: %s", msg)
            return False, msg

        # ── 2. notify_only always passes ──────────────────────────────────────
        if action_type == "notify_only":
            return True, "notify_only always permitted"

        # ── 3. Blocked namespaces ─────────────────────────────────────────────
        if namespace.lower() in BLOCKED_NAMESPACES:
            msg = f"Namespace '{namespace}' is in the blocked list — no automated actions permitted"
            log.warning("POLICY BLOCK: %s", msg)
            return False, msg

        # ── 4. Always-approval actions ────────────────────────────────────────
        if action_type in ALWAYS_REQUIRE_APPROVAL:
            msg = f"Action '{action_type}' requires explicit human approval"
            log.info("POLICY REQUIRE_APPROVAL: %s", msg)
            return False, msg

        # ── 5. Confidence threshold ───────────────────────────────────────────
        required_conf = (
            MIN_CONFIDENCE_HIGH_RISK
            if namespace.lower() in HIGH_RISK_NAMESPACES
            else MIN_CONFIDENCE_AUTO
        )
        if confidence < required_conf:
            msg = (
                f"Confidence {confidence:.2f} below threshold {required_conf:.2f} "
                f"for namespace '{namespace}'"
            )
            log.warning("POLICY BLOCK (low confidence): %s", msg)
            return False, msg

        # ── 6. Scale bounds ───────────────────────────────────────────────────
        if action_type in ("scale_up", "scale_down") and replicas is not None:
            if replicas > MAX_REPLICAS:
                msg = f"Requested replicas {replicas} exceeds MAX_REPLICAS {MAX_REPLICAS}"
                return False, msg
            if replicas < MIN_REPLICAS:
                msg = f"Requested replicas {replicas} below MIN_REPLICAS {MIN_REPLICAS}"
                return False, msg

        # ── 7. Require deployment name for mutating actions ───────────────────
        if action_type != "notify_only" and not deployment:
            msg = "Deployment name required for mutating actions"
            return False, msg

        log.info("POLICY ALLOW: action=%s ns=%s deploy=%s conf=%.2f",
                 action_type, namespace, deployment, confidence)
        return True, "allowed"

    def is_high_risk(self, namespace: str, action_type: str) -> bool:
        return (
            namespace.lower() in HIGH_RISK_NAMESPACES
            or action_type in ALWAYS_REQUIRE_APPROVAL
        )
