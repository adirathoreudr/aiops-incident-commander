# Demo Walkthrough

End-to-end demo from zero to resolved incident. Takes ~3 minutes once the stack is running.

> **Authentication.** `/webhook/simulate` and the executor's `/approve` require
> a bearer token. `docker compose up` supplies development defaults
> (`dev-collector-token` / `dev-executor-token`) so this walkthrough works as
> written; `scripts/simulate.sh` picks the collector one up automatically.
> Outside compose, export `COLLECTOR_API_TOKEN` to match your collector.

## Prerequisites

Stack running via `docker compose up -d` or deployed to EKS.

---

## Scenario 1 — CrashLoopBackOff (most common, highest impact)

### Step 1 — Inject the failure (10 seconds)

```bash
./scripts/simulate.sh crashloop
```

Or manually:

```bash
curl -X POST http://localhost:8000/webhook/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CrashLoopBackOff — payments-api after v2.4.0 deploy",
    "alertname": "KubePodCrashLooping",
    "severity": "critical",
    "namespace": "staging",
    "service": "payments-api",
    "deployment": "payments-api",
    "pod": "payments-api-7d9f84-xk2pq",
    "image_tag": "payments-api:v2.4.0"
  }'
```

Expected output:
```json
{"incident_id": "a3f8c2d1-...", "status": "enqueued"}
```

### Step 2 — Watch the collector normalise (< 2 seconds)

```bash
docker compose logs collector --tail=10
# 2026-04-19 10:00:01 INFO collector New incident a3f8c2d1 sev=critical CrashLoopBackOff in staging/payments-api
# 2026-04-19 10:00:01 INFO collector Enqueued incident a3f8c2d1 for agent
```

### Step 3 — Watch the agent reason (~15 seconds)

```bash
docker compose logs agent --tail=20
# 2026-04-19 10:00:02 INFO agent Reasoning over incident a3f8c2d1
# 2026-04-19 10:00:16 INFO agent LLM responded (923 chars) for incident a3f8c2d1
# 2026-04-19 10:00:16 INFO agent Incident a3f8c2d1 requires human approval (conf=0.94)
```

### Step 4 — Open dashboard

Navigate to `http://localhost:3001/dashboard`

You will see:
- New `CRITICAL` incident card at the top
- Confidence bar showing **94%**
- `RESTART ⏸` badge indicating approval pending

Click the card → incident detail view shows:

```
INCIDENT TYPE:   crash_loop
CONFIDENCE:      94%

ROOT CAUSE:
  v2.4.0 introduced a missing STRIPE_API_VERSION environment
  variable. Application panics on startup at config validation.
  Restart count 7 in 4 minutes.

EVIDENCE:
  › Log: 'FATAL: required env var STRIPE_API_VERSION not set'
  › Rollout: payments-api changed to v2.4.0 at 14:32 UTC
  › Alert: KubePodCrashLooping fired 90s after deploy

RECOMMENDED ACTION: RESTART ⏸ AWAITING APPROVAL
```

### Step 5 — Approve

Click **✓ APPROVE** in the dashboard.

The executor:
1. PolicyEngine checks: `rollout_restart` ✓ | `staging` not blocked ✓ | conf 0.94 ≥ 0.75 ✓
2. Patches deployment annotation → triggers rolling restart
3. Polls `ready_replicas` every 5s for up to 120s
4. Confirms recovery → status → `RESOLVED`

Dashboard shows:
```
◎ ACTION EXECUTED
Rollout restart triggered: staging/payments-api. Recovery confirmed.
```

### Step 6 — Review audit trail

Click **AUDIT** tab:
```
10:00:16  AI REASONED   type=crash_loop  conf=94%  → rollout_restart  ⏸
10:00:18  APPROVAL      APPROVED by operator@demo
10:00:19  ACTION        rollout_restart  staging/payments-api  ✓ SUCCESS
```

Total time from inject to resolved: **~3 minutes**.

---

## Scenario 2 — OOM Kill (auto-execute, no approval needed)

```bash
./scripts/simulate.sh oom_kill
```

Because `scale_up` in `staging` with confidence ≥ 0.75 is auto-executable, the executor fires **without human approval**.

Watch it resolve:
```bash
docker compose logs executor --tail=15
# Executing scale_up on staging/order-service
# Scaled staging/order-service to 6 replicas
# Recovery confirmed in 94 seconds
```

---

## Scenario 3 — Deployment Regression → ArgoCD Rollback

```bash
./scripts/simulate.sh deployment_regression
```

`argocd_rollback` is in `ALWAYS_REQUIRE_APPROVAL`. Even with conf=0.92, the executor will NOT auto-execute. Dashboard shows approval gate.

This demonstrates **human-in-the-loop** control for higher-risk actions.

---

## Scenario 4 — Alert Deduplication

Fire the same alert 5 times in quick succession:

```bash
for i in 1 2 3 4 5; do
  curl -s -X POST http://localhost:8000/webhook/alertmanager \
    -H "Content-Type: application/json" \
    -d '{
      "alerts": [{
        "labels": {
          "alertname": "KubePodCrashLooping",
          "namespace": "staging",
          "severity": "high",
          "service": "inventory-worker",
          "deployment": "inventory-worker"
        },
        "startsAt": "2026-04-19T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z"
      }]
    }' > /dev/null
done
```

Check the incident — `grouped_alert_count` will show **5** alerts merged into **1 incident**.
Dashboard shows: `×5 grouped` badge on the card.

This is the **40% noise reduction** mechanism in action.

---

## What This Demo Actually Shows

Behaviour you can observe directly, with no claim attached that has not been
measured. The percentage targets in the README are design goals, not results —
this walkthrough demonstrates the mechanisms, not a benchmark.

| What | How you see it |
|------|----------------|
| Alert correlation | 5 identical alerts → one incident card with `×5 grouped` |
| Evidence-backed triage | Root cause cites the specific log lines and rollout events it rests on |
| Triage latency | `docker compose logs agent` timestamp delta, alert → hypothesis |
| Policy gating | `argocd_rollback` requires approval regardless of confidence |
| Approval actually works | Clicking APPROVE moves the incident to execution, not to `escalated` |
| Blocked namespaces hold | A `kube-system` target is refused even with approval |
| Full auditability | AUDIT tab shows every decision, approval and action with timestamps |

To turn the targets into measurements you would need a harness that replays a
population of incidents through the live loop and records dedup ratio, triage
latency and auto-resolve rate. That does not exist yet — it is on the roadmap.
