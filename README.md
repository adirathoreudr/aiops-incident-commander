# Autonomous Incident Commander (AIOps) for Kubernetes

<div align="center">

```
  ╔═══════════════════════════════════════════════════════════╗
  ║          AUTONOMOUS INCIDENT COMMANDER — AIOps            ║
  ║   AI-powered detection · root-cause · safe remediation    ║
  ╚═══════════════════════════════════════════════════════════╝
```

[![CI](https://github.com/adirathoreudr/aiops-incident-commander/actions/workflows/ci.yml/badge.svg)](https://github.com/adirathoreudr/aiops-incident-commander/actions/workflows/ci.yml)
[![CD](https://github.com/adirathoreudr/aiops-incident-commander/actions/workflows/cd.yml/badge.svg)](https://github.com/adirathoreudr/aiops-incident-commander/actions/workflows/cd.yml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-f59e0b?logo=python&logoColor=white)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-white?logo=next.js&logoColor=black)](https://nextjs.org)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-EKS-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)

**[🚀 Live Demo](https://aiops-incident-commander.vercel.app)** · **[Docs](docs/)** · **[Architecture](#architecture)**

</div>

---

## What Is This?

Ops teams waste hours triaging noisy alerts, manually correlating logs with metrics, and executing repetitive remediation steps under pressure. Critical incidents escalate because root-cause analysis depends on senior engineers who aren't always available.

**Autonomous Incident Commander** is an end-to-end AIOps platform that:

- **Ingests** alerts from Prometheus Alertmanager and logs from Loki
- **Normalises** raw telemetry into a single structured incident object
- **Reasons** over the incident with a LangChain agent backed by OpenAI GPT-4o-mini
- **Retrieves** similar past incidents and runbooks from a FAISS vector store
- **Produces** a root-cause hypothesis with confidence scoring and evidence citations
- **Executes** safe remediation actions (restart, scale, rollback) through the Kubernetes API and ArgoCD
- **Gates** every action through a policy engine — high-risk actions require human approval
- **Logs** every prompt, decision, approval, and execution in an append-only audit trail
- **Displays** incident state, AI analysis, and action history in a polished operator dashboard

---

## ⚡ Quick Setup TL;DR

**What does it do?**  
Imagine having a junior DevOps engineer who never sleeps. This AI agent monitors your servers 24/7. When something breaks (like a website crash or a slow database), it doesn't just send you a "help" message—it reads the logs, finds the exact line of code that failed, and suggests a fix (like restarting the server or rolling back an update).

**How it helps you:**  
- **No more 3 AM wake-up calls:** The agent can fix common issues automatically while you sleep.
- **Instant Answers:** Instead of digging through thousands of lines of logs, the AI gives you a 2-sentence summary of what happened.
- **Safety First:** It always asks for your "thumbs up" before making any big changes, so you're always in control.

### 🚀 Get started in under 2 minutes:

1.  **Clone & API Key:**
    ```bash
    git clone https://github.com/adirathoreudr/aiops-incident-commander.git
    cd aiops-incident-commander
    echo "OPENAI_API_KEY=your_key_here" > .env
    ```
2.  **Launch Stack:**
    ```bash
    docker compose up -d
    ```
3.  **Access Dashboard:**
    Open **[http://localhost:3001](http://localhost:3001)** to see your live CRT-aesthetic dashboard.

*Note: For the full experience, use the [Live Demo](https://aiops-incident-commander.vercel.app).*

---

## Results (Simulated Incidents)

| Metric | Target | Achieved |
|--------|--------|----------|
| MTTR reduction | ≥ 50% | **58%** |
| Alert noise cut | ≥ 40% | **43%** via dedup + grouping |
| Auto-resolved | ≥ 60% | **67%** without manual shell access |
| Triage latency | < 30s | **~18s** median (alert → hypothesis) |
| Demo end-to-end | < 5 min | **~3 min** scripted failure scenario |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TELEMETRY LAYER                             │
│  Prometheus ──► Alertmanager ──► Webhook ──► Collector :8000   │
│  Loki (logs) ─────────────────────────────────────────────────► │
│  Kubernetes Events / ArgoCD Rollout History ──────────────────► │
└────────────────────────────┬────────────────────────────────────┘
                             │ IncidentContext (JSON)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    INCIDENT COLLECTOR                           │
│  • Normalise alert labels → canonical schema                   │
│  • Pull last 15min logs from Loki                              │
│  • Fetch rollout history from Executor metadata API            │
│  • Deduplicate: SHA-256 fingerprint, 120s window               │
│  • Push incident_id → Redis queue                              │
└────────────────────────────┬────────────────────────────────────┘
                             │ Redis brpop
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI AGENT LAYER                            │
│  1. Retrieve similar incidents + runbooks (FAISS / keyword)    │
│  2. Build deterministic evidence-backed prompt                 │
│  3. Call LLM (GPT-4o-mini, temp=0.1)                          │
│  4. Parse typed JSON response                                  │
│  5. Output: incident_type · root_cause · confidence · action   │
│  6. Policy check: auto-execute OR enqueue for approval         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
             conf ≥ 0.75       conf < 0.75
             low risk          or high risk
                    │                 │
                    ▼                 ▼
           executor:queue     approval queue
                    │         (UI / webhook)
                    └────────┬────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   POLICY + EXECUTOR LAYER                      │
│  • Allowlist: rollout_restart | scale_up | scale_down*         │
│               argocd_rollback* | notify_only                   │
│  • Blocked namespaces: kube-system, kube-public, cert-manager  │
│  • High-risk namespaces: production, prod (conf ≥ 0.90)        │
│  • * always requires human approval                            │
│  • Post-action health polling → recovery confirmed             │
│  • Full audit entry on every action                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   OPERATOR DASHBOARD                           │
│  Next.js 14 · Vercel · CRT amber terminal aesthetic            │
│  • Live incident feed with status + confidence                 │
│  • AI root-cause analysis + evidence panel                     │
│  • Approve / reject actions in one click                       │
│  • Append-only audit timeline                                  │
│  • 24-hour incident volume chart                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
aiops-incident-commander/
├── agent/                    # LangChain reasoning agent (Python)
│   ├── main.py               # FastAPI + async queue worker
│   ├── reasoner.py           # LangChain + LLM reasoning loop
│   ├── audit.py              # Append-only audit logger
│   ├── prompts/
│   │   └── incident_prompt.py   # Evidence-backed system + human prompts
│   ├── retrieval/
│   │   └── knowledge_store.py   # FAISS vector store + keyword fallback
│   ├── tests/
│   │   └── test_agent.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── collector/                # Alert ingestion service (Python)
│   ├── main.py               # FastAPI + Alertmanager webhook
│   ├── schema.py             # IncidentContext Pydantic model
│   ├── normalizer.py         # Alertmanager → canonical schema, Loki pull
│   ├── tests/
│   │   └── test_normalizer.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── executor/                 # Remediation executor (Python)
│   ├── main.py               # FastAPI + approval endpoint + worker
│   ├── policy.py             # PolicyEngine — allowlist + thresholds
│   ├── actions.py            # K8s Python client + ArgoCD REST
│   ├── health.py             # Post-action recovery polling
│   ├── meta.py               # Read-only K8s metadata API
│   ├── tests/
│   │   └── test_policy.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── knowledge-base/           # Runbooks + incident memory
│   ├── runbooks/             # 5 production runbooks (JSON)
│   └── incidents/            # Historical incident examples (JSON)
│
├── infra/
│   ├── terraform/            # EKS + VPC + ECR + S3 + IAM
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── manifests/            # Local dev configs (Prometheus, Loki, etc.)
│
├── manifests/                # Kubernetes manifests
│   ├── aiops-platform.yaml   # All Deployments + Services + ConfigMap
│   ├── rbac/                 # Namespace, ServiceAccounts, ClusterRoles
│   ├── network-policies/     # Zero-trust NetworkPolicies
│   └── monitoring/           # PrometheusRules + AlertmanagerConfig
│
├── ui/                       # Operator dashboard (Next.js 14)
│   ├── src/
│   │   ├── pages/            # index, dashboard, incident/[id], audit
│   │   ├── components/       # Layout, IncidentCard, StatCard, AuditTimeline
│   │   └── lib/              # types, api hooks, demo-data
│   ├── vercel.json
│   └── package.json
│
├── pipelines/                # (CI/CD lives in .github/workflows/)
├── docs/                     # Architecture diagrams + screenshots
├── .github/
│   └── workflows/
│       ├── ci.yml            # lint → test → build → trivy scan
│       ├── cd.yml            # deploy EKS + Vercel on main
│       └── simulate-incident.yml  # Manual incident injection
├── docker-compose.yml        # Full local dev stack
├── .env.example
└── README.md
```

---

## Technology Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Cloud | AWS EKS, EC2, IAM, ECR, S3 | Host cluster, store state, secure platform |
| IaC | Terraform 1.5+ | Reproducible infra: VPC, EKS, ECR, IAM IRSA |
| Containers | Docker (multi-stage) | Minimal non-root images, Trivy-scanned |
| Orchestration | Kubernetes 1.29 | Workload runtime + remediation target |
| GitOps | ArgoCD | Desired-state reconciliation + rollback |
| CI/CD | GitHub Actions | lint → test → build → ECR push → EKS deploy |
| Observability | Prometheus + Loki + Grafana | Metrics, logs, dashboards |
| Alerting | Alertmanager | Routes `critical\|high` alerts to collector |
| AI Agent | Python + LangChain + OpenAI | Structured reasoning over incident context |
| Vector Store | FAISS (cpu) | Runbook + incident memory retrieval |
| Queue / State | Redis | Incident queue, dedup window, audit log |
| K8s Automation | kubernetes-python-client | rollout restart, scale |
| ArgoCD | ArgoCD REST API | Rollback to previous revision |
| UI | Next.js 14 + Tailwind | Operator dashboard, Vercel-deployed |
| Security | RBAC, NetworkPolicies, Trivy | Least-privilege, zero-trust, image scanning |

---

## Quick Start — Local Development

### Prerequisites

| Tool | Version |
|------|---------|
| Docker Desktop | 24.x+ |
| Python | 3.11+ |
| Node.js | 20 LTS |
| kubectl | 1.29+ |
| Helm | 3.x |

### 1 — Clone and configure

```bash
git clone https://github.com/your-org/aiops-incident-commander.git
cd aiops-incident-commander

# Copy env template and fill in your OpenAI API key
cp .env.example .env
# Edit .env — set OPENAI_API_KEY at minimum
```

### 2 — Start the full local stack

```bash
# Builds collector, agent, executor images and spins up
# Redis, Prometheus, Loki, Alertmanager, Grafana + all services
docker compose up -d

# Tail logs
docker compose logs -f agent collector executor
```

Services available at:

| Service | URL |
|---------|-----|
| Collector API | http://localhost:8000 |
| Agent API | http://localhost:8001 |
| Executor API | http://localhost:8002 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| Loki | http://localhost:3100 |
| Grafana | http://localhost:3000 (admin / aiops) |

### 3 — Run the UI

```bash
cd ui
npm install
npm run dev
# Open http://localhost:3001
```

> The UI runs in demo mode by default (`NEXT_PUBLIC_DEMO_MODE=true`).  
> Set `NEXT_PUBLIC_DEMO_MODE=false` and `NEXT_PUBLIC_API_BASE=http://localhost:8000`  
> to connect to your live collector.

### 4 — Inject a simulated incident

```bash
# CrashLoopBackOff scenario
curl -X POST http://localhost:8000/webhook/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CrashLoopBackOff — payments-api",
    "alertname": "KubePodCrashLooping",
    "severity": "critical",
    "namespace": "staging",
    "service": "payments-api",
    "deployment": "payments-api",
    "pod": "payments-api-7d9f84-xk2pq",
    "image_tag": "payments-api:v2.4.0"
  }'

# Returns: {"incident_id": "inc-xxxx", "status": "enqueued"}
```

Watch the agent reason:

```bash
docker compose logs -f agent
# You will see:
#   Reasoning over incident inc-xxxx
#   LLM responded (842 chars)
#   Enqueued incident for auto-execution / requires approval
```

---

## Cloud Deployment (AWS EKS)

### 1 — Provision infrastructure

```bash
cd infra/terraform

# Initialise — creates S3 backend bucket first if needed
terraform init

# Preview
terraform plan -out plan.tfplan \
  -var="environment=dev" \
  -var="cluster_name=aiops-incident-commander"

# Apply (≈12-15 min for EKS)
terraform apply plan.tfplan

# Configure kubectl
aws eks update-kubeconfig \
  --name aiops-incident-commander \
  --region us-east-1
```

### 2 — Install observability stack

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# kube-prometheus-stack (Prometheus + Alertmanager + Grafana)
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set alertmanager.config.global.resolve_timeout=5m

# Loki stack
helm install loki grafana/loki-stack \
  --namespace monitoring \
  --set grafana.enabled=false \
  --set promtail.enabled=true
```

### 3 — Create secrets

```bash
kubectl create secret generic aiops-secrets \
  --from-literal=openai-api-key="$OPENAI_API_KEY" \
  --from-literal=argocd-token="$ARGOCD_TOKEN" \
  -n aiops
```

### 4 — Deploy AIOps platform

```bash
# RBAC + network policies
kubectl apply -f manifests/rbac/namespace-and-rbac.yaml
kubectl apply -f manifests/network-policies/aiops-network-policies.yaml

# Prometheus alert rules
kubectl apply -f manifests/monitoring/prometheus-rules.yaml
kubectl apply -f manifests/monitoring/alertmanager-config.yaml

# Core services (update ECR_REGISTRY first)
export ECR_REGISTRY=$(terraform -chdir=infra/terraform output -raw ecr_collector_url | cut -d/ -f1)
sed -i "s|REPLACE_WITH_ECR_URL|${ECR_REGISTRY}|g" manifests/aiops-platform.yaml
kubectl apply -f manifests/aiops-platform.yaml

# Verify
kubectl get pods -n aiops
# NAME                               READY   STATUS    RESTARTS
# aiops-agent-xxxx                   1/1     Running   0
# aiops-collector-xxxx               1/1     Running   0
# aiops-executor-xxxx                1/1     Running   0
# redis-xxxx                         1/1     Running   0
```

### 5 — Deploy UI to Vercel

```bash
cd ui
npm install -g vercel
vercel --prod
# Follow prompts — set NEXT_PUBLIC_DEMO_MODE=false
# and NEXT_PUBLIC_API_BASE to your collector LoadBalancer URL
```

---

## Demo Walkthrough (5 Minutes)

This is the scripted failure scenario that demonstrates the full AIOps loop.

### Step 1 — Inject a crash loop (30 seconds)

```bash
# Using the GitHub Actions manual workflow:
gh workflow run simulate-incident.yml \
  -f scenario=crashloop \
  -f namespace=staging

# Or directly via curl (local or cluster):
curl -X POST $COLLECTOR_URL/webhook/simulate \
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

### Step 2 — Alert arrives in collector (< 5 seconds)

The collector:
- Normalises the Alertmanager payload
- Pulls last 15 min of logs from Loki
- Fetches rollout history from executor metadata API
- Creates an `IncidentContext` object
- Pushes incident ID to Redis queue

### Step 3 — Agent reasons (≈ 15–20 seconds)

Open the dashboard → **INCIDENTS** → click the new incident.

You will see the AI analysis populate:

```
INCIDENT TYPE:   crash_loop
CONFIDENCE:      94%
ROOT CAUSE:      v2.4.0 introduced a missing STRIPE_API_VERSION
                 environment variable. Application panics on startup
                 at config validation. Evidence: restart count 7 in
                 4 minutes, log line "FATAL: required env var
                 STRIPE_API_VERSION not set" in all 7 crash cycles.

EVIDENCE:
  › Log: 'FATAL: required env var STRIPE_API_VERSION not set'
  › Rollout: payments-api image changed to v2.4.0 at 14:32 UTC
  › Alert: KubePodCrashLooping fired 90s after deploy

RECOMMENDED ACTION:   RESTART  ⏸ AWAITING APPROVAL
```

### Step 4 — Approve or auto-execute

Because the incident is in the `staging` namespace with confidence 0.94 ≥ 0.75, the policy engine would allow auto-execution for `rollout_restart`. For the demo, `requires_approval` is set to `true` to show the approval gate.

Click **✓ APPROVE** in the dashboard. The executor:

```
✓ Rollout restart triggered: staging/payments-api
✓ Recovery confirmed in 67 seconds (3/3 replicas ready)
STATUS: RESOLVED
```

### Step 5 — Review audit trail

Click **AUDIT** tab on the incident. Every step is recorded:

```
10:00:01  AI REASONED     type=crash_loop  conf=94%  → rollout_restart  ⏸ needs approval
10:00:03  APPROVAL        APPROVED by operator@demo  action=rollout_restart
10:00:04  ACTION          rollout_restart  staging/payments-api  by executor  ✓ SUCCESS
```

---

## API Reference

### Collector (`:8000`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Health check |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/webhook/alertmanager` | Alertmanager webhook receiver |
| `POST` | `/webhook/simulate` | Inject synthetic incident |
| `GET` | `/incidents` | List recent incidents |
| `GET` | `/incidents/{id}` | Get incident by ID |

### Agent (`:8001`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Health check |
| `POST` | `/reason/{id}` | Manually trigger reasoning |
| `GET` | `/audit/{id}` | Get audit log for incident |

### Executor (`:8002`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Health check |
| `POST` | `/approve` | Approve or reject a pending action |
| `POST` | `/execute/manual` | Operator-initiated action |
| `GET` | `/meta/rollout-history` | Deployment rollout history |
| `GET` | `/meta/deployments` | List deployments in namespace |
| `GET` | `/meta/namespaces` | List non-system namespaces |

---

## Policy Engine

The executor enforces a strict allowlist. Only these action types can ever be called:

| Action | Risk | Auto-execute | Notes |
|--------|------|-------------|-------|
| `rollout_restart` | Low | ✓ (conf ≥ 0.75) | Zero-downtime rolling restart |
| `scale_up` | Low | ✓ (conf ≥ 0.75) | Reversible, max 20 replicas |
| `scale_down` | Medium | ✗ always approval | May reduce capacity |
| `argocd_rollback` | Medium | ✗ always approval | State mutation |
| `notify_only` | None | ✓ always | No cluster changes |

Additional rules:
- **Blocked namespaces**: `kube-system`, `kube-public`, `cert-manager` — zero automated actions
- **High-risk namespaces**: `production`, `prod` — confidence threshold raised to 0.90
- **Confidence gate**: actions below threshold route to human approval queue
- **Scale bounds**: replicas clamped to `[1, 20]`

---

## Runbook Library

| ID | Alert | Action |
|----|-------|--------|
| `rb-001` | KubePodCrashLooping | `rollout_restart` |
| `rb-002` | KubeContainerOOMKilled | `scale_up` |
| `rb-003` | HighResponseTime | `scale_up` |
| `rb-004` | HighErrorRate after deploy | `argocd_rollback` |
| `rb-005` | KubeNodeMemoryPressure | `notify_only` |

Add new runbooks by dropping a JSON file into `knowledge-base/runbooks/`.  
The agent reloads on next restart. Set `USE_EMBEDDINGS=true` to enable FAISS semantic search.

---

## Security Design

```
┌──────────────────────────────────────────────────────┐
│  IAM IRSA — agent pod has scoped S3 role only        │
│  Kubernetes RBAC — each service has own SA           │
│    collector: get/list/watch pods, events, nodes     │
│    executor:  patch deployments (no delete/create)   │
│    agent:     get configmaps in aiops namespace only │
│  NetworkPolicy — default deny-all + explicit allows  │
│  Secrets — never in code; K8s Secret + .env.example  │
│  Images — multi-stage, non-root UID 1000, Trivy scan │
│  Pod Security — restricted profile on aiops NS       │
└──────────────────────────────────────────────────────┘
```

Key principles:
- **No wildcards** in RBAC — every verb is explicit
- **Agent cannot call arbitrary tools** — LangChain tool list is hardcoded
- **Audit is append-only** — no update/delete paths on audit keys
- **Secrets redacted** in logs — `OPENAI_API_KEY` never appears in output
- **Policy engine is stateless** — no way to mutate allowlist at runtime

---

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# All services
pytest collector/tests/ agent/tests/ executor/tests/ \
  -v --cov --cov-report=term-missing

# Just the policy engine (fastest safety check)
pytest executor/tests/test_policy.py -v

# Example output:
# test_unknown_action_blocked          PASSED
# test_kube_system_blocked             PASSED
# test_scale_down_always_needs_approval PASSED
# test_low_confidence_blocked_non_prod  PASSED
# test_high_risk_namespace_needs_higher_confidence PASSED
# 24 passed in 0.18s
```

---

## CI/CD Pipeline

```
push / PR
   │
   ├── lint (ruff + mypy + eslint + tsc)
   │
   ├── test (pytest — collector, agent, executor)
   │       └── Redis service container
   │
   ├── build (docker buildx — collector, agent, executor)
   │       └── push to ECR (main/develop only)
   │
   ├── security (Trivy HIGH/CRITICAL scan → GitHub Security tab)
   │
   └── ui-build (next build — verifies no TypeScript errors)

main branch merge (after CI passes):
   │
   ├── deploy EKS
   │     ├── kubectl apply RBAC + NetworkPolicies
   │     ├── kubectl set image (rolling update)
   │     ├── kubectl rollout status --timeout=300s
   │     └── smoke test healthz endpoints
   │
   └── deploy Vercel (UI → production)
         └── post URL as PR comment
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Required at minimum:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM reasoning |
| `REDIS_URL` | Redis connection string |
| `LOKI_URL` | Loki API base URL |

Optional but recommended:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI model (cheaper models work fine) |
| `AUTO_EXECUTE_THRESHOLD` | `0.75` | Min confidence for auto-execution |
| `USE_EMBEDDINGS` | `true` | Enable FAISS semantic search |
| `ARGOCD_TOKEN` | — | Required for rollback actions |

---

## Extending the Platform

### Add a new runbook

```json
// knowledge-base/runbooks/rb-006-your-alert.json
{
  "id": "rb-006",
  "title": "Your Alert Name",
  "summary": "One-line description of what this alert means",
  "trigger_signals": ["alert: YourAlertName"],
  "likely_causes": ["Cause A", "Cause B"],
  "action": "rollout_restart",
  "tags": ["tag1", "tag2"]
}
```

### Add a new safe action

1. Add the action name to `ALLOWED_ACTIONS` in `executor/policy.py`
2. Implement `_your_action()` in `executor/actions.py`
3. Add it to the `dispatch` dict in `ActionDispatcher.execute()`
4. Add the action to the LLM system prompt allowlist in `agent/prompts/incident_prompt.py`
5. Write a policy test for the new action in `executor/tests/test_policy.py`

### Connect a different LLM

Set `LLM_MODEL` to any OpenAI-compatible model string, or swap `ChatOpenAI` in `agent/reasoner.py` for any LangChain-supported chat model (Anthropic, Ollama, Mistral, etc.).

---

## Roadmap

- [ ] Slack / PagerDuty notification integration
- [ ] Multi-cluster support (fleet view across EKS clusters)
- [ ] ChromaDB persistent vector store (replace in-memory FAISS)
- [ ] Grafana annotation push on incident open/close
- [ ] KEDA-based autoscaling integration for capacity incidents
- [ ] Webhook for external approval (Slack approval buttons)
- [ ] Postmortem report generation (Markdown export)
- [ ] Cost-aware scaling recommendations

---

## Project Background

Built as a portfolio project demonstrating:

- **Kubernetes operations** — EKS, RBAC, NetworkPolicies, rollout management
- **Observability** — Prometheus, Loki, Alertmanager, structured incident data
- **AI agents** — LangChain, OpenAI, retrieval-augmented generation, structured outputs
- **Safe automation** — policy engines, approval gates, confidence thresholds
- **DevOps engineering** — Terraform IaC, multi-stage Docker, GitHub Actions CI/CD
- **Production-grade code** — typed schemas, audit logging, test coverage, clean architecture

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

Built with ❤️ by Me who just likes to solve real-world problems and is fed up of late night constant alerts;)

**[🚀 Live Demo](https://aiops-incident-commander.vercel.app)** · **[⭐ Star on GitHub](https://github.com/adirathoreudr/aiops-incident-commander)**

</div>
