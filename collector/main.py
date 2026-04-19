"""
collector/main.py
FastAPI service: receives Alertmanager webhooks, normalises telemetry,
deduplicates, and enqueues incidents for the AI agent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from .schema import AlertLabel, IncidentContext, Severity
from .normalizer import (
    normalize_alertmanager_payload,
    fetch_loki_logs,
    fetch_k8s_rollout_history,
)

# ── Config ────────────────────────────────────────────────────────────────────
REDIS_URL      = os.getenv("REDIS_URL", "redis://localhost:6379")
LOKI_URL       = os.getenv("LOKI_URL", "http://loki:3100")
K8S_API_URL    = os.getenv("K8S_API_URL", "http://aiops-executor:8002")
DEDUP_WINDOW_S = int(os.getenv("DEDUP_WINDOW_SECONDS", "120"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("collector")

# ── Metrics ───────────────────────────────────────────────────────────────────
alerts_received   = Counter("aiops_alerts_received_total",  "Alerts received",  ["severity"])
incidents_created = Counter("aiops_incidents_created_total","Incidents created")
incidents_deduped = Counter("aiops_incidents_deduped_total","Alerts deduped")
processing_time   = Histogram("aiops_collection_duration_seconds", "Processing latency")

redis_client: aioredis.Redis | None = None

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    log.info("Collector started — Redis %s", REDIS_URL)
    yield
    if redis_client:
        await redis_client.aclose()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AIOps Incident Collector",
    description="Normalises telemetry from Alertmanager + Loki into incident context objects",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Error handlers ────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def _exc_handler(request: Request, exc: Exception):
    log.exception("Unhandled: %s %s — %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

@app.exception_handler(ValueError)
async def _val_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "collector"}

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.post("/webhook/alertmanager")
async def alertmanager_webhook(request: Request, background: BackgroundTasks):
    """Alertmanager webhook — returns 200 immediately, processes async."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=422, content={"detail": "Invalid JSON"})
    background.add_task(_safe_process, body)
    return {"status": "accepted"}

@app.post("/webhook/simulate")
async def simulate_incident(payload: dict):
    """Inject a synthetic incident for demo/testing."""
    incident = IncidentContext(
        title=payload.get("title", "Simulated Incident"),
        severity=Severity(payload.get("severity", "high")),
        namespace=payload.get("namespace", "default"),
        service=payload.get("service"),
        deployment=payload.get("deployment"),
        pod=payload.get("pod"),
        image_tag=payload.get("image_tag"),
        alerts=[AlertLabel(
            alertname=payload.get("alertname", "SimulatedAlert"),
            namespace=payload.get("namespace", "default"),
            severity=Severity(payload.get("severity", "high")),
            service=payload.get("service"),
        )],
    )
    await _persist_and_enqueue(incident)
    return {"incident_id": incident.incident_id, "status": "enqueued"}

@app.get("/incidents")
async def list_incidents(limit: int = 20):
    keys = await redis_client.keys("incident:*")
    incidents = []
    for k in sorted(keys, reverse=True)[:limit]:
        raw = await redis_client.get(k)
        if raw:
            try:
                incidents.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return {"incidents": incidents, "count": len(incidents)}

@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    raw = await redis_client.get(f"incident:{incident_id}")
    if not raw:
        raise HTTPException(404, "Incident not found")
    return json.loads(raw)

# ── Processing ────────────────────────────────────────────────────────────────
async def _safe_process(body: dict) -> None:
    try:
        await _do_process(body)
    except Exception as e:
        log.exception("Processing error: %s", e)

async def _do_process(body: dict) -> None:
    with processing_time.time():
        for alert_raw in body.get("alerts", []):
            severity_str = alert_raw.get("labels", {}).get("severity", "warning")
            alerts_received.labels(severity=severity_str).inc()

            alert = normalize_alertmanager_payload(alert_raw)
            fp    = _fingerprint(alert)

            existing_id = await redis_client.get(f"fingerprint:{fp}")
            if existing_id:
                await _merge(existing_id, alert)
                incidents_deduped.inc()
                continue

            logs     = await fetch_loki_logs(LOKI_URL, alert.namespace, alert.service)
            rollouts = await fetch_k8s_rollout_history(K8S_API_URL, alert.namespace, alert.deployment)

            incident = IncidentContext(
                title=f"{alert.alertname} in {alert.namespace}/{alert.service or alert.pod or 'unknown'}",
                severity=alert.severity,
                namespace=alert.namespace,
                service=alert.service,
                deployment=alert.deployment,
                pod=alert.pod,
                node=alert.node,
                alerts=[alert],
                logs=logs,
                rollout_events=rollouts,
                fingerprint=fp,
            )
            await _persist_and_enqueue(incident)
            incidents_created.inc()
            log.info("New incident %s sev=%s %s", incident.incident_id, incident.severity, incident.title)

async def _merge(incident_id: str, alert: AlertLabel) -> None:
    raw = await redis_client.get(f"incident:{incident_id}")
    if not raw:
        return
    incident = IncidentContext(**json.loads(raw))
    incident.alerts.append(alert)
    incident.grouped_alert_count += 1
    incident.mark_updated()
    await redis_client.setex(f"incident:{incident_id}", 3600, incident.model_dump_json())

async def _persist_and_enqueue(incident: IncidentContext) -> None:
    await redis_client.setex(f"incident:{incident.incident_id}", 3600, incident.model_dump_json())
    if incident.fingerprint:
        await redis_client.setex(f"fingerprint:{incident.fingerprint}", DEDUP_WINDOW_S, incident.incident_id)
    await redis_client.lpush("agent:queue", incident.incident_id)

def _fingerprint(alert: AlertLabel) -> str:
    key = f"{alert.alertname}|{alert.namespace}|{alert.service}|{alert.deployment}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
