"""
executor/main.py
FastAPI service that:
  1. Pops approved incidents from Redis queue
  2. Validates actions against policy allowlist
  3. Executes safe actions via Kubernetes Python client + ArgoCD REST
  4. Verifies recovery with post-action health checks
  5. Writes result back to Redis and audit log
  6. Exposes /approve endpoint for human approval flow
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

from .policy import PolicyEngine
from .actions import ActionDispatcher
from .health import HealthChecker
from .meta import MetaRouter

log = logging.getLogger("executor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

REDIS_URL     = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = float(os.getenv("QUEUE_POLL_INTERVAL", "2.0"))

# ── Metrics ───────────────────────────────────────────────────────────────────

actions_executed  = Counter("aiops_actions_executed_total", "Actions executed", ["action_type", "success"])
actions_blocked   = Counter("aiops_actions_blocked_total", "Actions blocked by policy")
execution_latency = Histogram("aiops_execution_duration_seconds", "Action execution latency")

# ── Lifespan ──────────────────────────────────────────────────────────────────

redis_client: aioredis.Redis | None = None
worker_task:  asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, worker_task
    redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    worker_task = asyncio.create_task(executor_worker())
    log.info("Executor started")
    yield
    worker_task.cancel()
    await redis_client.aclose()


app = FastAPI(
    title="AIOps Remediation Executor",
    description="Policy-gated executor for safe Kubernetes and ArgoCD remediation actions",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(MetaRouter, prefix="/meta", tags=["metadata"])


# ── Approval models ───────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    incident_id: str
    approved: bool
    approver: str = "operator"


class ManualActionRequest(BaseModel):
    incident_id: str
    action_type: str
    deployment: str
    namespace: str
    replicas: int | None = None
    approver: str = "operator"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "executor"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")


@app.post("/approve")
async def approve_action(req: ApprovalRequest):
    """
    Human approval endpoint. Operator approves or rejects a pending action.
    If approved, incident is pushed to executor queue.
    """
    raw = await redis_client.get(f"incident:{req.incident_id}")
    if not raw:
        raise HTTPException(404, "Incident not found")

    incident = json.loads(raw)

    # Audit the approval decision
    await _append_audit(req.incident_id, {
        "ts":          datetime.now(timezone.utc).isoformat(),
        "event_type":  "approval_decision",
        "approved":    req.approved,
        "approver":    req.approver,
        "action_type": incident.get("recommended_action"),
    })

    if req.approved:
        incident["requires_approval"] = False
        incident["approved_by"] = req.approver
        incident["approved_at"] = datetime.now(timezone.utc).isoformat()
        incident["status"] = "remediating"
        await redis_client.setex(f"incident:{req.incident_id}", 3600, json.dumps(incident))
        await redis_client.lpush("executor:queue", req.incident_id)
        log.info("Incident %s approved by %s — enqueued for execution", req.incident_id, req.approver)
        return {"status": "approved", "enqueued": True}
    else:
        incident["status"] = "escalated"
        incident["rejected_by"] = req.approver
        await redis_client.setex(f"incident:{req.incident_id}", 3600, json.dumps(incident))
        log.info("Incident %s rejected by %s", req.incident_id, req.approver)
        return {"status": "rejected"}


@app.post("/execute/manual")
async def manual_execute(req: ManualActionRequest):
    """Direct execution endpoint for operator-initiated actions."""
    policy = PolicyEngine()
    dispatcher = ActionDispatcher()

    allowed, reason = policy.check(req.action_type, req.namespace, req.deployment, confidence=1.0)
    if not allowed:
        actions_blocked.inc()
        raise HTTPException(403, f"Policy blocked action: {reason}")

    with execution_latency.time():
        result = await dispatcher.execute(
            action_type=req.action_type,
            namespace=req.namespace,
            deployment=req.deployment,
            replicas=req.replicas,
        )

    await _append_audit(req.incident_id, {
        "ts":          datetime.now(timezone.utc).isoformat(),
        "event_type":  "action_executed",
        "action_type": req.action_type,
        "target":      f"{req.namespace}/{req.deployment}",
        "actor":       req.approver,
        "success":     result["success"],
        "result":      result["message"],
    })

    actions_executed.labels(action_type=req.action_type, success=str(result["success"])).inc()
    return result


@app.get("/incidents/{incident_id}/audit")
async def get_audit(incident_id: str):
    raw = await redis_client.get(f"audit:{incident_id}")
    return {"entries": json.loads(raw) if raw else []}


# ── Worker ────────────────────────────────────────────────────────────────────

async def executor_worker() -> None:
    policy     = PolicyEngine()
    dispatcher = ActionDispatcher()
    checker    = HealthChecker()

    log.info("Executor worker started")
    while True:
        try:
            item = await redis_client.brpop("executor:queue", timeout=POLL_INTERVAL)
            if not item:
                continue

            _, incident_id = item
            raw = await redis_client.get(f"incident:{incident_id}")
            if not raw:
                continue

            incident = json.loads(raw)
            action_type = incident.get("recommended_action", "notify_only")
            params      = incident.get("recommended_action_params", {})
            namespace   = params.get("namespace") or incident.get("namespace", "default")
            deployment  = params.get("deployment") or incident.get("deployment", "")
            confidence  = incident.get("confidence_score", 0.0)

            # Final policy gate
            allowed, reason = policy.check(action_type, namespace, deployment, confidence)
            if not allowed:
                actions_blocked.inc()
                log.warning("Action blocked by policy for %s: %s", incident_id, reason)
                incident["status"] = "escalated"
                incident["policy_block_reason"] = reason
                await redis_client.setex(f"incident:{incident_id}", 3600, json.dumps(incident))
                continue

            log.info("Executing %s on %s/%s for incident %s", action_type, namespace, deployment, incident_id)

            with execution_latency.time():
                result = await dispatcher.execute(
                    action_type=action_type,
                    namespace=namespace,
                    deployment=deployment,
                    replicas=params.get("replicas"),
                )

            actions_executed.labels(action_type=action_type, success=str(result["success"])).inc()

            # Verify recovery
            if result["success"]:
                recovered = await checker.wait_for_recovery(namespace, deployment)
                result["recovered"] = recovered
                incident["status"] = "resolved" if recovered else "escalated"
            else:
                incident["status"] = "escalated"

            # Persist result
            incident["last_action"] = {
                "type":    action_type,
                "result":  result["message"],
                "success": result["success"],
                "ts":      datetime.now(timezone.utc).isoformat(),
            }
            await redis_client.setex(f"incident:{incident_id}", 3600, json.dumps(incident))

            # Audit
            await _append_audit(incident_id, {
                "ts":          datetime.now(timezone.utc).isoformat(),
                "event_type":  "action_executed",
                "action_type": action_type,
                "target":      f"{namespace}/{deployment}",
                "actor":       "executor",
                "success":     result["success"],
                "result":      result["message"],
                "recovered":   result.get("recovered"),
            })

            log.info("Incident %s → status=%s action=%s success=%s",
                     incident_id, incident["status"], action_type, result["success"])

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.exception("Executor worker error: %s", e)
            await asyncio.sleep(1.0)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _append_audit(incident_id: str, entry: dict) -> None:
    key  = f"audit:{incident_id}"
    raw  = await redis_client.get(key)
    log_ = json.loads(raw) if raw else []
    log_.append(entry)
    await redis_client.setex(key, 86400 * 30, json.dumps(log_))
