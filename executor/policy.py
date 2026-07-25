"""
executor/policy.py
Policy engine: validates every action before execution.
Blocks anything not on the allowlist.
Enforces confidence thresholds and namespace restrictions.
"""

from __future__ import annotations

from enum import Enum
import logging
import os

log = logging.getLogger("executor.policy")


class Decision(str, Enum):
    """
    The verdict on a proposed action.

    Splitting REQUIRE_APPROVAL out from BLOCK matters because the executor
    re-runs the policy gate *after* a human approves. With a single boolean the
    two are indistinguishable, so an action that merely needed sign-off stays
    refused once it has been signed off, and the incident dead-ends as
    escalated. Keeping them apart lets the gate stay in place — approval is not
    a bypass for the namespace allowlist — while still letting an approved
    action through.
    """

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"

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
    "scale_down",  # may reduce capacity in prod
    "argocd_rollback",  # state mutation — human must confirm
}


class PolicyEngine:
    """
    Stateless policy checker.

    ``evaluate`` is the real entry point; ``check`` is a boolean view of it kept
    for callers that only care whether an action may proceed right now.
    """

    def evaluate(
        self,
        action_type: str,
        namespace: str,
        deployment: str,
        confidence: float,
        replicas: int | None = None,
        *,
        approved: bool = False,
    ) -> tuple[Decision, str]:
        """
        Decide what should happen to a proposed action.

        ``approved`` says a human has explicitly signed off. It relaxes the
        checks that exist to summon a human — the always-approve list and the
        confidence floor — and nothing else. Every hard rule below is evaluated
        first precisely so that approval cannot be used to talk the platform
        into touching kube-system or running an action nobody allowlisted.
        """

        # ── Hard rules: no approval can unlock these ──────────────────────────

        if action_type not in ALLOWED_ACTIONS:
            msg = f"Action '{action_type}' not in approved action allowlist"
            log.warning("POLICY BLOCK: %s", msg)
            return Decision.BLOCK, msg

        if action_type == "notify_only":
            return Decision.ALLOW, "notify_only always permitted"

        if namespace.lower() in BLOCKED_NAMESPACES:
            msg = f"Namespace '{namespace}' is in the blocked list — no automated actions permitted"
            log.warning("POLICY BLOCK: %s", msg)
            return Decision.BLOCK, msg

        if not deployment:
            msg = "Deployment name required for mutating actions"
            log.warning("POLICY BLOCK: %s", msg)
            return Decision.BLOCK, msg

        if action_type in ("scale_up", "scale_down") and replicas is not None:
            if replicas > MAX_REPLICAS:
                msg = (
                    f"Requested replicas {replicas} exceeds MAX_REPLICAS {MAX_REPLICAS}"
                )
                log.warning("POLICY BLOCK: %s", msg)
                return Decision.BLOCK, msg
            if replicas < MIN_REPLICAS:
                msg = f"Requested replicas {replicas} below MIN_REPLICAS {MIN_REPLICAS}"
                log.warning("POLICY BLOCK: %s", msg)
                return Decision.BLOCK, msg

        # ── Soft rules: satisfied by a human signing off ──────────────────────

        if action_type in ALWAYS_REQUIRE_APPROVAL and not approved:
            msg = f"Action '{action_type}' requires explicit human approval"
            log.info("POLICY REQUIRE_APPROVAL: %s", msg)
            return Decision.REQUIRE_APPROVAL, msg

        required_conf = (
            MIN_CONFIDENCE_HIGH_RISK
            if namespace.lower() in HIGH_RISK_NAMESPACES
            else MIN_CONFIDENCE_AUTO
        )
        if confidence < required_conf and not approved:
            msg = (
                f"Confidence {confidence:.2f} below threshold {required_conf:.2f} "
                f"for namespace '{namespace}' — routing to human approval"
            )
            log.info("POLICY REQUIRE_APPROVAL (low confidence): %s", msg)
            return Decision.REQUIRE_APPROVAL, msg

        log.info(
            "POLICY ALLOW: action=%s ns=%s deploy=%s conf=%.2f approved=%s",
            action_type,
            namespace,
            deployment,
            confidence,
            approved,
        )
        return Decision.ALLOW, "allowed"

    def check(
        self,
        action_type: str,
        namespace: str,
        deployment: str,
        confidence: float,
        replicas: int | None = None,
    ) -> tuple[bool, str]:
        """
        Boolean view of ``evaluate``: may this action proceed unattended?

        Both BLOCK and REQUIRE_APPROVAL come back as False, which is the right
        answer for an unattended caller — but callers acting on a human decision
        need ``evaluate`` so they can tell the two apart.
        """
        decision, reason = self.evaluate(
            action_type, namespace, deployment, confidence, replicas
        )
        return decision is Decision.ALLOW, reason

    def is_high_risk(self, namespace: str, action_type: str) -> bool:
        return (
            namespace.lower() in HIGH_RISK_NAMESPACES
            or action_type in ALWAYS_REQUIRE_APPROVAL
        )
