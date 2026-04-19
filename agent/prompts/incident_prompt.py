"""
agent/prompts/incident_prompt.py
Deterministic prompts that force the LLM to cite evidence from
metrics, logs, and rollout history before recommending action.
"""

from __future__ import annotations

import json
import re
from typing import Any


SYSTEM_PROMPT = """\
You are a senior SRE incident analyst. Your role is to triage Kubernetes incidents
using only the evidence provided — logs, metrics, alerts, and rollout history.

## Rules
1. You MUST cite specific evidence from the incident context for every claim you make.
2. You MUST choose the SAFEST possible remediation from the approved action list.
3. You MUST NOT recommend destructive or irreversible actions.
4. If evidence is insufficient, set confidence_score below 0.5 and set requires_approval to true.
5. Your response MUST be valid JSON only — no markdown, no explanation outside the JSON.

## Approved Remediation Actions
- rollout_restart: Restart a deployment (safe, zero-downtime)
- scale_up: Increase replica count (safe, reversible)
- scale_down: Decrease replica count (reversible but may impact capacity)
- argocd_rollback: Roll back to last known good ArgoCD revision (reversible)
- notify_only: Post incident summary without taking action

## Output Schema
{
  "incident_type": "<crash_loop|oom_kill|high_latency|node_pressure|config_error|unknown>",
  "probable_root_cause": "<1-3 sentence explanation citing specific evidence>",
  "confidence_score": <0.0-1.0>,
  "supporting_evidence": [
    "<evidence item 1 from logs/metrics/alerts>",
    "<evidence item 2>",
    "<evidence item 3 if available>"
  ],
  "recommended_action": "<one of the approved actions above>",
  "recommended_action_params": {
    "deployment": "<deployment name>",
    "namespace": "<namespace>",
    "replicas": <int if scaling>
  },
  "requires_approval": <true|false>,
  "approval_reason": "<why human approval is needed, if requires_approval is true>"
}
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_human_prompt(
    incident: dict[str, Any],
    similar_incidents: list[dict],
    runbooks: list[dict],
) -> str:
    """Assembles the full human-turn prompt with all context."""
    parts = []

    # ── Incident context ──────────────────────────────────────────────────────
    parts.append("## CURRENT INCIDENT")
    parts.append(f"ID:         {incident.get('incident_id', 'unknown')}")
    parts.append(f"Title:      {incident.get('title', 'unknown')}")
    parts.append(f"Severity:   {incident.get('severity', 'unknown')}")
    parts.append(f"Namespace:  {incident.get('namespace', 'unknown')}")
    parts.append(f"Service:    {incident.get('service', 'unknown')}")
    parts.append(f"Deployment: {incident.get('deployment', 'unknown')}")
    parts.append(f"Pod:        {incident.get('pod', 'unknown')}")
    parts.append(f"Image Tag:  {incident.get('image_tag', 'unknown')}")
    parts.append("")

    # ── Alerts ────────────────────────────────────────────────────────────────
    parts.append("### ACTIVE ALERTS")
    for a in incident.get("alerts", [])[:5]:
        parts.append(f"  - [{a.get('severity', '?')}] {a.get('alertname', '?')} (ns={a.get('namespace', '?')})")
    parts.append("")

    # ── Logs ──────────────────────────────────────────────────────────────────
    parts.append("### RECENT LOGS (last 15 lines)")
    logs = incident.get("logs", [])
    for entry in logs[-15:]:
        ts  = entry.get("timestamp", "")[:19] if entry.get("timestamp") else "?"
        lvl = entry.get("level", "info").upper()
        msg = entry.get("message", "")[:300]
        parts.append(f"  [{ts}] [{lvl}] {msg}")
    if not logs:
        parts.append("  (no logs available)")
    parts.append("")

    # ── Rollout history ───────────────────────────────────────────────────────
    parts.append("### ROLLOUT HISTORY (last 3 events)")
    rollouts = incident.get("rollout_events", [])
    for r in rollouts[-3:]:
        parts.append(
            f"  - deployment={r.get('deployment')} "
            f"rev={r.get('revision')} "
            f"image={r.get('image')} "
            f"status={r.get('status')} "
            f"at={str(r.get('started_at', ''))[:19]}"
        )
    if not rollouts:
        parts.append("  (no rollout events available)")
    parts.append("")

    # ── Similar past incidents ─────────────────────────────────────────────────
    if similar_incidents:
        parts.append("### SIMILAR PAST INCIDENTS")
        for sim in similar_incidents[:3]:
            parts.append(f"  Past incident: {sim.get('title', '?')}")
            parts.append(f"    Root cause: {sim.get('probable_root_cause', '?')}")
            parts.append(f"    Resolution: {sim.get('resolved_by', '?')}")
            parts.append("")

    # ── Relevant runbooks ─────────────────────────────────────────────────────
    if runbooks:
        parts.append("### RELEVANT RUNBOOKS")
        for rb in runbooks[:2]:
            parts.append(f"  Runbook: {rb.get('title', '?')}")
            parts.append(f"    Summary: {rb.get('summary', '?')}")
            parts.append(f"    Recommended action: {rb.get('action', '?')}")
            parts.append("")

    parts.append("---")
    parts.append("Analyse the above incident and respond with a valid JSON object matching the schema.")

    return "\n".join(parts)


def parse_agent_response(raw: str) -> dict[str, Any]:
    """
    Parse LLM JSON response. Falls back to safe defaults on parse failure.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    try:
        data = json.loads(cleaned)
        # Validate and clamp confidence
        conf = float(data.get("confidence_score", 0.0))
        data["confidence_score"] = max(0.0, min(1.0, conf))
        return data
    except (json.JSONDecodeError, ValueError):
        # Extract confidence from text if JSON failed
        return {
            "incident_type": "unknown",
            "probable_root_cause": "Unable to parse LLM response. Manual review required.",
            "confidence_score": 0.0,
            "supporting_evidence": [],
            "recommended_action": "notify_only",
            "recommended_action_params": {},
            "requires_approval": True,
            "approval_reason": "LLM response parse failure",
        }
