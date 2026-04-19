"""
agent/main.py
FastAPI service wrapping the LangChain-based incident reasoning agent.
Pops incidents from Redis queue, reasons over context, stores results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from .reasoner import IncidentReasoner
from .audit import AuditLogger

# ── Config ────────────────────────────────────────────────────────────────────

REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379")
COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://aiops-collector:8000")
EXECUTOR_URL  = os.getenv("EXECUTOR_URL", "http://aiops-executor:8002")
POLL_INTERVAL = float(os.getenv("QUEUE_POLL_INTERVAL", "2.0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("agent")

# ── Metrics ───────────────────────────────────────────────────────────────────

incidents_processed = Counter("aiops_agent_incidents_processed_total", "Incidents processed by agent")
reasoning_errors    = Counter("aiops_agent_reasoning_errors_total", "Reasoning failures")
reasoning_latency   = Histogram("aiops_agent_reasoning_seconds", "Agent reasoning latency")

# ── Lifespan ──────────────────────────────────────────────────────────────────

redis_client: aioredis.Redis | None = None
worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, worker_task
    redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    worker_task = asyncio.create_task(queue_worker())
    log.info("Agent started — queue worker running")
    yield
    worker_task.cancel()
    await redis_client.aclose()


app = FastAPI(
    title="AIOps Incident Reasoning Agent",
    description="LangChain-based agent that produces root-cause hypotheses and recommends safe remediation",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "agent"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")


@app.post("/reason/{incident_id}")
async def trigger_reasoning(incident_id: str):
    """Manually trigger reasoning for an incident (useful for demo/testing)."""
    await redis_client.lpush("agent:queue", incident_id)
    return {"status": "enqueued", "incident_id": incident_id}


@app.get("/audit/{incident_id}")
async def get_audit(incident_id: str):
    """Return full audit log for an incident."""
    raw = await redis_client.get(f"audit:{incident_id}")
    if not raw:
        return {"entries": []}
    return json.loads(raw)


# ── Queue worker ──────────────────────────────────────────────────────────────

async def queue_worker() -> None:
    """Continuously pops incident IDs from Redis and processes them."""
    reasoner = IncidentReasoner()
    auditor  = AuditLogger(redis_client)

    log.info("Queue worker started")
    while True:
        try:
            item = await redis_client.brpop("agent:queue", timeout=POLL_INTERVAL)
            if not item:
                continue

            _, incident_id = item
            raw = await redis_client.get(f"incident:{incident_id}")
            if not raw:
                log.warning("Incident %s not found in Redis", incident_id)
                continue

            log.info("Reasoning over incident %s", incident_id)
            with reasoning_latency.time():
                result = await reasoner.reason(json.loads(raw))

            # Persist enriched incident back to Redis
            await redis_client.setex(f"incident:{incident_id}", 3600, json.dumps(result))

            # Store audit record
            await auditor.record(incident_id, result)

            # If auto-executable action, enqueue executor
            if (
                not result.get("requires_approval")
                and result.get("recommended_action")
                and result.get("confidence_score", 0) >= 0.7
            ):
                await redis_client.lpush("executor:queue", incident_id)
                log.info("Enqueued incident %s for auto-execution", incident_id)
            else:
                log.info("Incident %s requires human approval (conf=%.2f)", incident_id, result.get("confidence_score", 0))

            incidents_processed.inc()

        except asyncio.CancelledError:
            break
        except Exception as e:
            reasoning_errors.inc()
            log.exception("Queue worker error: %s", e)
            await asyncio.sleep(1.0)
