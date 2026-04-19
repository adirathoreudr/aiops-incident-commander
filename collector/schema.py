"""
collector/schema.py
Canonical incident schema. Every alert/log anomaly is normalized into
an IncidentContext before being passed to the agent layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"
    INFO = "info"


class IncidentStatus(str, Enum):
    OPEN = "open"
    IN_TRIAGE = "in_triage"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class AlertLabel(BaseModel):
    alertname: str
    namespace: str = "default"
    severity: Severity = Severity.WARNING
    service: str | None = None
    pod: str | None = None
    deployment: str | None = None
    node: str | None = None
    container: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class LogEntry(BaseModel):
    timestamp: datetime
    stream: dict[str, str] = Field(default_factory=dict)  # Loki labels
    message: str
    level: str = "info"


class MetricSample(BaseModel):
    name: str
    value: float
    labels: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime


class RolloutEvent(BaseModel):
    deployment: str
    namespace: str
    image: str
    revision: int
    started_at: datetime
    status: str  # "progressing" | "complete" | "failed"


class RemediationAction(BaseModel):
    action_type: str         # restart | scale | rollback | notify
    target: str              # deployment/<name> or app/<name>
    parameters: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    approved_by: str | None = None
    executed_at: datetime | None = None
    result: str | None = None
    success: bool | None = None


class IncidentContext(BaseModel):
    """
    Single canonical object representing one normalized incident.
    Created by the collector, enriched by the agent, acted on by the executor.
    """
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    status: IncidentStatus = IncidentStatus.OPEN

    # Identity
    title: str
    severity: Severity
    namespace: str
    service: str | None = None
    deployment: str | None = None
    pod: str | None = None
    node: str | None = None
    image_tag: str | None = None

    # Raw signals
    alerts: list[AlertLabel] = Field(default_factory=list)
    logs: list[LogEntry] = Field(default_factory=list)
    metrics: list[MetricSample] = Field(default_factory=list)
    rollout_events: list[RolloutEvent] = Field(default_factory=list)

    # Agent output
    incident_type: str | None = None
    probable_root_cause: str | None = None
    confidence_score: float | None = None   # 0.0 – 1.0
    supporting_evidence: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    requires_approval: bool = True

    # Remediation
    actions: list[RemediationAction] = Field(default_factory=list)

    # Dedup
    fingerprint: str | None = None
    grouped_alert_count: int = 1

    def mark_updated(self) -> None:
        self.updated_at = _utcnow()

    def to_prompt_context(self) -> str:
        """Serialize incident for LLM prompt injection."""
        lines = [
            f"INCIDENT ID: {self.incident_id}",
            f"TITLE: {self.title}",
            f"SEVERITY: {self.severity.value}",
            f"NAMESPACE: {self.namespace}",
            f"SERVICE: {self.service or 'unknown'}",
            f"DEPLOYMENT: {self.deployment or 'unknown'}",
            f"POD: {self.pod or 'unknown'}",
            f"IMAGE TAG: {self.image_tag or 'unknown'}",
            "",
            "ALERTS:",
        ]
        for a in self.alerts[:5]:
            lines.append(f"  - [{a.severity.value}] {a.alertname}")
        lines.append("")
        lines.append("RECENT LOGS (last 10):")
        for log in self.logs[-10:]:
            lines.append(f"  [{log.level}] {log.message[:200]}")
        lines.append("")
        lines.append("RECENT ROLLOUT EVENTS:")
        for r in self.rollout_events[-3:]:
            lines.append(f"  - {r.deployment} rev={r.revision} image={r.image} status={r.status} at={r.started_at}")
        return "\n".join(lines)
