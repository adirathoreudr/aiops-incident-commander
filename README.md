# Autonomous Incident Commander (AIOps) for Kubernetes

[![CI](https://github.com/adirathoreudr/aiops-incident-commander/actions/workflows/ci.yml/badge.svg)](https://github.com/adirathoreudr/aiops-incident-commander/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-f59e0b?logo=python&logoColor=white)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-white?logo=next.js&logoColor=black)](https://nextjs.org)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-EKS-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)

An AI agent that triages Kubernetes incidents and remediates the safe ones,
without giving anything shell access.

Alertmanager alerts are correlated into incidents, enriched with Loki logs and
rollout history, reasoned over by an LLM that must cite its evidence, and — if a
policy engine agrees — remediated through a fixed allowlist of reversible
actions. Every decision, approval and action is recorded.

**Nothing here is autonomous by default.** High-risk actions require a human,
production namespaces demand higher confidence, `kube-system` is off limits
entirely, and the model can only ever escalate to review, never away from it.

---

## Quick start

```bash
git clone https://github.com/adirathoreudr/aiops-incident-commander.git
cd aiops-incident-commander

echo "OPENAI_API_KEY=sk-..." > .env      # or ANTHROPIC_API_KEY + LLM_MODEL=claude-...

docker compose up -d
```

Dashboard at **http://localhost:3001**. Compose supplies development API tokens,
so there is nothing else to configure locally.

Inject an incident and watch the loop run:

```bash
./scripts/simulate.sh crashloop
docker compose logs -f agent executor
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3001 |
| Collector / Agent / Executor | :8000 / :8001 / :8002 |
| Prometheus / Alertmanager / Loki | :9090 / :9093 / :3100 |
| Grafana | :3000 (admin / aiops) |

The dashboard reads from the collector — there is no demo dataset. An empty feed
means no incidents; the header reads `DISCONNECTED` if the collector is
unreachable.

---

## How it works

```
Alertmanager ─► collector ─► agent ─► policy gate ─► executor ─► Kubernetes
                    │           │          │             │
                 dedup +     LLM +      allowlist     verify
                 Loki logs   runbooks   + confidence   recovery
                    └───────────── audit trail ────────────┘
```

1. **Collect** — normalise the Alertmanager payload, fingerprint it to
   deduplicate related alerts into one incident, attach the last 15 minutes of
   Loki logs and recent rollout history.
2. **Reason** — retrieve similar past incidents and runbooks, prompt the LLM with
   the evidence, parse a typed hypothesis with a confidence score. Unparseable
   output falls back to `notify_only` with confidence 0.
3. **Gate** — the policy engine returns `ALLOW`, `REQUIRE_APPROVAL` or `BLOCK`.
   Approval relaxes only the rules that exist to summon a human; the allowlist
   and blocked namespaces hold regardless of who approves.
4. **Execute** — patch the deployment via the Kubernetes API, then poll until it
   is healthy or the timeout expires.
5. **Record** — every step is appended to a Redis list, atomically, so the agent
   and executor cannot overwrite each other.

Services communicate through Redis (queues, dedup window, incident state, audit).

**Stack:** Python 3.11 · FastAPI · LangChain · FAISS · Redis · Next.js 14 ·
Kubernetes · ArgoCD · Terraform · Prometheus/Loki/Grafana · GitHub Actions.

---

## Policy engine

Only these actions can ever be dispatched. Anything else is refused before it
reaches the cluster.

| Action | Auto-execute | Notes |
|--------|--------------|-------|
| `rollout_restart` | ✓ conf ≥ 0.75 | Zero-downtime rolling restart |
| `scale_up` | ✓ conf ≥ 0.75 | Reversible, capped at 20 replicas |
| `scale_down` | ✗ approval | May shed capacity mid-incident |
| `argocd_rollback` | ✗ approval | State mutation |
| `notify_only` | ✓ always | No cluster changes |

- **Blocked namespaces** — `kube-system`, `kube-public`, `cert-manager`. No
  approval unlocks these.
- **High-risk namespaces** — `production`, `prod` require confidence ≥ 0.90.
- **Scale bounds** — replicas clamped to `[1, 20]`.
- **Defence in depth** — RBAC binds remediation writes per-namespace, so the
  executor cannot patch a namespace nobody granted it even if the policy engine
  has a bug.

---

## Authentication

The executor patches live deployments, so the paths that reach it need a bearer
token. Generate one per environment with `openssl rand -hex 32`.

| Variable | Guards | If unset |
|----------|--------|----------|
| `EXECUTOR_API_TOKEN` | `POST /approve`, `POST /execute/manual` | **Fails closed** — 503 on every request |
| `COLLECTOR_API_TOKEN` | `POST /webhook/simulate`; also `/webhook/alertmanager` and reads once set | `simulate` refused; ingestion stays open |

**The executor fails closed deliberately.** Treating "no token" as "no checks"
would leave an unauthenticated cluster-mutation endpoint in every deployment that
forgot to configure one. An unconfigured executor still ingests, reasons and
reports — it just cannot act.

`/webhook/alertmanager` is the exception: Alertmanager needs matching config to
send a credential, and a platform that silently stops seeing production alerts is
worse than an open ingest path. Once `COLLECTOR_API_TOKEN` is set, configure
Alertmanager to match:

```yaml
webhook_configs:
  - url: http://aiops-collector:8000/webhook/alertmanager
    http_config:
      authorization: { type: Bearer, credentials_file: /etc/alertmanager/secrets/collector-token }
```

`/healthz` and `/metrics` are never authenticated — probes and scrapes carry no
credentials. Browser origins are restricted via `CORS_ALLOWED_ORIGINS`.

The dashboard proxies through its own API routes (`ui/src/pages/api/`) rather
than calling the services directly, so tokens stay server-side. That is why they
have no `NEXT_PUBLIC_` prefix — Next would inline them into the client bundle.

---

## API

**Collector `:8000`**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/webhook/alertmanager` | if token set | Alertmanager receiver |
| `POST` | `/webhook/simulate` | **required** | Inject a synthetic incident |
| `GET` | `/incidents` | if token set | Recent incidents, newest first |
| `GET` | `/incidents/{id}` | if token set | One incident |

**Agent `:8001`** — `POST /reason/{id}` (re-queue), `GET /audit/{id}`.

**Executor `:8002`**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/approve` | **required** | Approve or reject a pending action |
| `POST` | `/execute/manual` | **required** | Operator-initiated action |
| `GET` | `/audit` | if token set | Audit entries across all incidents |
| `GET` | `/incidents/{id}/audit` | if token set | Audit trail for one incident |
| `GET` | `/meta/*` | — | Rollout history, deployments, namespaces |

All three expose `/healthz` and `/metrics`.

---

## Configuration

Full list in [`.env.example`](.env.example). Required:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | LLM credential (or `ANTHROPIC_API_KEY` + a `claude-*` `LLM_MODEL`) |
| `EXECUTOR_API_TOKEN` | Without it the executor refuses all remediation |
| `REDIS_URL`, `LOKI_URL` | Backing services |

Worth knowing:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_EXECUTE_THRESHOLD` | `0.75` | Minimum confidence for unattended execution |
| `INCIDENT_TTL_SECONDS` | `3600` | Incident retention (audit is kept 30 days) |
| `USE_EMBEDDINGS` | `true` | FAISS semantic search. Needs `OPENAI_API_KEY` even with an Anthropic model, since embeddings come from OpenAI; otherwise it logs a warning and falls back to keyword matching |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3001` | Permitted browser origins |
| `ARGOCD_TOKEN` / `ARGOCD_CA_BUNDLE` | — | Required for rollback. TLS verification is on; point the bundle at your CA rather than disabling it |

---

## Deploying to EKS

```bash
# 1. Infrastructure (~15 min)
cd infra/terraform && terraform init && terraform apply

# 2. Observability
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
helm install loki grafana/loki-stack -n monitoring --set grafana.enabled=false

# 3. Secrets — created out of band, never part of `apply`
kubectl create secret generic aiops-secrets -n aiops \
  --from-literal=openai-api-key="$OPENAI_API_KEY" \
  --from-literal=executor-api-token="$(openssl rand -hex 32)" \
  --from-literal=collector-api-token="$(openssl rand -hex 32)"

# 4. Platform — kustomize generates the knowledge-base ConfigMaps and
#    resolves image references. Applying the raw manifests skips both.
for svc in collector agent executor; do
  kustomize edit set image \
    "REPLACE_WITH_ECR_URL/aiops-incident-commander/$svc=$ECR_REGISTRY/aiops-incident-commander/$svc:latest"
done
kubectl apply -k .

# 5. Alert routing
kubectl apply -f manifests/monitoring/
kubectl create secret generic alertmanager-aiops-token -n monitoring \
  --from-literal=token="$COLLECTOR_API_TOKEN"
```

Before your first deploy, update the Ingress hostnames in
`manifests/aiops-platform.yaml`, and note that RBAC binds remediation writes to
the **`staging` namespace only** — copy that RoleBinding into any other namespace
you want remediated. See [`manifests/secret.example.yaml`](manifests/secret.example.yaml)
for the full set of secret keys.

The UI deploys to Vercel with `COLLECTOR_URL`, `EXECUTOR_URL`,
`COLLECTOR_API_TOKEN` and `EXECUTOR_API_TOKEN` as **server-side** environment
variables (no `NEXT_PUBLIC_` prefix).

---

## Development

```bash
pytest                                    # 142 tests
ruff check collector/ agent/ executor/
cd ui && npm run type-check && npm run build

# Kubernetes manifests — no cluster required
kubectl kustomize . > /tmp/rendered.yaml
kubeconform -strict -kubernetes-version 1.29.0 /tmp/rendered.yaml
python scripts/validate_manifests.py /tmp/rendered.yaml
```

`validate_manifests.py` exists because schema validity is not deployability:
every Deployment here was once schema-valid *and* rejected at admission for
omitting what the `restricted` Pod Security profile requires. It also refuses a
Secret in the applied set, since applying one overwrites real credentials.

CI runs lint → test → ui-build → manifest validation → build. Images are scanned
with Trivy **before** being pushed, so a CRITICAL finding never reaches the
registry.

**Add a runbook** — drop a JSON file into `knowledge-base/runbooks/`. Kustomize
hashes the contents, so the agent rolls automatically.

**Add an action** — allowlist it in `executor/policy.py`, implement it in
`executor/actions.py`, add it to the dispatch table and the prompt in
`agent/prompts/incident_prompt.py`, and write a policy test.

---

## Design targets

| Metric | Target |
|--------|--------|
| MTTR reduction | ≥ 50% |
| Alert noise cut via dedup + grouping | ≥ 40% |
| Auto-resolved without shell access | ≥ 60% |
| Triage latency (alert → hypothesis) | < 30s |

These are goals, **not measurements** — no benchmark harness exists in this
repository. What is verified is the test suite and CI: the loop has been
exercised end to end against real services (Alertmanager webhook → dedup →
approval → execution → audit), and the manifests are schema- and
policy-validated on every push.

**This is production-ready, not production-proven.** It has never handled a real
incident on a real cluster. Point it at a staging namespace first.

---

## Roadmap

- Prometheus metric ingestion — the schema has `MetricSample`; nothing populates
  it, and the prompt tells the model not to cite metrics for that reason
- A benchmark harness, so the targets above can become measurements
- SSO/OIDC on the approval flow (currently a shared bearer token)
- Shared package for the duplicated `audit.py` / `cors.py` — each service builds
  from its own Docker context and cannot import from the others
- Slack / PagerDuty notifications, multi-cluster fleet view, postmortem export

See [`docs/DEMO.md`](docs/DEMO.md) for a scripted walkthrough and
[`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) for
component detail.

---

## License

MIT — see [LICENSE](LICENSE).
