"""
collector/normalizer.py
Parses raw Alertmanager payloads, fetches Loki logs, and pulls
Kubernetes rollout history from the executor's metadata API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import httpx

from .schema import AlertLabel, LogEntry, RolloutEvent, Severity

log = logging.getLogger("collector.normalizer")

LOKI_LOOKBACK_MINUTES = 15
MAX_LOG_LINES = 100


def normalize_alertmanager_payload(raw: dict[str, Any]) -> AlertLabel:
    """Convert a single Alertmanager alert dict into an AlertLabel."""
    labels = raw.get("labels", {})
    return AlertLabel(
        alertname=labels.get("alertname", "UnknownAlert"),
        namespace=labels.get("namespace", labels.get("exported_namespace", "default")),
        severity=_parse_severity(labels.get("severity", "warning")),
        service=labels.get("service") or labels.get("app") or labels.get("job"),
        pod=labels.get("pod"),
        deployment=labels.get("deployment") or labels.get("app"),
        node=labels.get("node") or labels.get("instance"),
        container=labels.get("container"),
        # The running image is the single strongest signal for "did a deploy
        # cause this", so pick it up wherever the exporter happens to put it.
        image_tag=(
            labels.get("image_tag")
            or labels.get("image")
            or labels.get("container_image")
        ),
        extra={
            k: v
            for k, v in labels.items()
            if k
            not in {
                "alertname",
                "namespace",
                "severity",
                "service",
                "app",
                "pod",
                "deployment",
                "node",
                "instance",
                "container",
                "container_image",
                "image",
                "image_tag",
                "job",
            }
        },
    )


def _parse_severity(raw: str) -> Severity:
    mapping = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "warning": Severity.WARNING,
        "warn": Severity.WARNING,
        "info": Severity.INFO,
        "none": Severity.INFO,
    }
    return mapping.get(raw.lower(), Severity.WARNING)


async def fetch_loki_logs(
    loki_url: str,
    namespace: str,
    service: str | None,
    lookback_minutes: int = LOKI_LOOKBACK_MINUTES,
) -> list[LogEntry]:
    """
    Query Loki for logs matching namespace + service label in the lookback window.
    Returns up to MAX_LOG_LINES entries sorted oldest-first.
    """
    if not service:
        label_selector = f'{{namespace="{namespace}"}}'
    else:
        label_selector = f'{{namespace="{namespace}", app="{service}"}}'

    end_ns = int(datetime.now(timezone.utc).timestamp() * 1e9)
    start_ns = int(
        (datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)).timestamp()
        * 1e9
    )

    params = {
        "query": label_selector,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": str(MAX_LOG_LINES),
        "direction": "backward",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{loki_url}/loki/api/v1/query_range", params=params
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning(
            "Loki query failed (namespace=%s service=%s): %s", namespace, service, e
        )
        return []

    entries: list[LogEntry] = []
    for stream in data.get("data", {}).get("result", []):
        stream_labels = stream.get("stream", {})
        for ts_nano, line in stream.get("values", []):
            ts = datetime.utcfromtimestamp(int(ts_nano) / 1e9)
            level = _infer_log_level(line, stream_labels)
            entries.append(
                LogEntry(
                    timestamp=ts,
                    stream=stream_labels,
                    message=line,
                    level=level,
                )
            )

    # Sort oldest-first, cap at MAX_LOG_LINES
    entries.sort(key=lambda e: e.timestamp)
    return entries[-MAX_LOG_LINES:]


def _infer_log_level(line: str, labels: dict) -> str:
    lvl = labels.get("level", "").lower()
    if lvl in {"error", "fatal", "critical", "warn", "warning", "info", "debug"}:
        return lvl
    low = line.lower()
    for kw in ("error", "exception", "fatal", "panic", "critical"):
        if kw in low:
            return "error"
    for kw in ("warn", "warning"):
        if kw in low:
            return "warn"
    return "info"


async def fetch_k8s_rollout_history(
    executor_url: str,
    namespace: str,
    deployment: str | None,
) -> list[RolloutEvent]:
    """
    Ask the executor service for recent rollout events.
    Returns last 5 events for the deployment (or all in namespace if unknown).
    """
    if not deployment:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{executor_url}/meta/rollout-history",
                params={"namespace": namespace, "deployment": deployment},
            )
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        log.warning(
            "Rollout history fetch failed (%s/%s): %s", namespace, deployment, e
        )
        return []

    events = []
    for item in raw.get("events", [])[:5]:
        try:
            events.append(
                RolloutEvent(
                    deployment=item["deployment"],
                    namespace=item["namespace"],
                    image=item.get("image", "unknown"),
                    revision=item.get("revision", 0),
                    started_at=datetime.fromisoformat(item["started_at"]),
                    status=item.get("status", "unknown"),
                )
            )
        except Exception:
            continue
    return events
