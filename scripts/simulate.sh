#!/usr/bin/env bash
# scripts/simulate.sh
# End-to-end demo simulation script.
# Injects a failure scenario and tails logs to show the full AIOps loop.
# Usage: ./scripts/simulate.sh [scenario] [collector_url]
#   scenario: crashloop | oom_kill | high_latency | deployment_regression
#   collector_url: defaults to http://localhost:8000

set -euo pipefail

SCENARIO="${1:-crashloop}"
COLLECTOR_URL="${2:-http://localhost:8000}"
NAMESPACE="${3:-staging}"

# ── Colours ───────────────────────────────────────────────────────────────────
AMBER='\033[0;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
RESET='\033[0m'
BOLD='\033[1m'

banner() {
  echo -e "\n${AMBER}${BOLD}╔══════════════════════════════════════════════╗${RESET}"
  echo -e "${AMBER}${BOLD}║   AIOps Incident Commander — Demo Simulation  ║${RESET}"
  echo -e "${AMBER}${BOLD}╚══════════════════════════════════════════════╝${RESET}\n"
}

step() { echo -e "${CYAN}[STEP]${RESET} $1"; }
ok()   { echo -e "${GREEN}[ OK ]${RESET} $1"; }
info() { echo -e "       $1"; }

# ── Scenario payloads ─────────────────────────────────────────────────────────
declare -A PAYLOADS

PAYLOADS[crashloop]='{
  "title": "CrashLoopBackOff — payments-api after v2.4.0 deploy",
  "alertname": "KubePodCrashLooping",
  "severity": "critical",
  "namespace": "'"$NAMESPACE"'",
  "service": "payments-api",
  "deployment": "payments-api",
  "pod": "payments-api-7d9f84-xk2pq",
  "image_tag": "payments-api:v2.4.0"
}'

PAYLOADS[oom_kill]='{
  "title": "OOMKilled — 2/3 order-service pods hit memory limit",
  "alertname": "KubeContainerOOMKilled",
  "severity": "high",
  "namespace": "'"$NAMESPACE"'",
  "service": "order-service",
  "deployment": "order-service",
  "pod": "order-service-5c7d9b-m3np1",
  "image_tag": "order-service:v3.1.2"
}'

PAYLOADS[high_latency]='{
  "title": "High p95 latency — user-service breaching 500ms SLO",
  "alertname": "HighResponseTime",
  "severity": "high",
  "namespace": "'"$NAMESPACE"'",
  "service": "user-service",
  "deployment": "user-service",
  "image_tag": "user-service:v1.8.4"
}'

PAYLOADS[deployment_regression]='{
  "title": "HighErrorRate — api-gateway 5xx spike after deploy",
  "alertname": "HighErrorRate",
  "severity": "high",
  "namespace": "'"$NAMESPACE"'",
  "service": "api-gateway",
  "deployment": "api-gateway",
  "image_tag": "api-gateway:v5.2.0"
}'

# ── Main ──────────────────────────────────────────────────────────────────────
banner

echo -e "Scenario:  ${AMBER}${BOLD}${SCENARIO}${RESET}"
echo -e "Collector: ${COLLECTOR_URL}"
echo -e "Namespace: ${NAMESPACE}\n"

if [[ -z "${PAYLOADS[$SCENARIO]+x}" ]]; then
  echo -e "${RED}Unknown scenario: $SCENARIO${RESET}"
  echo "Available: crashloop | oom_kill | high_latency | deployment_regression"
  exit 1
fi

# 1. Check collector health
step "Checking collector health..."
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "${COLLECTOR_URL}/healthz" || echo "000")
if [[ "$HTTP" != "200" ]]; then
  echo -e "${RED}Collector not reachable at ${COLLECTOR_URL} (HTTP $HTTP)${RESET}"
  echo "Start the stack with: docker compose up -d"
  exit 1
fi
ok "Collector is healthy"

# 2. Inject incident
step "Injecting ${SCENARIO} incident..."
RESPONSE=$(curl -sf -X POST "${COLLECTOR_URL}/webhook/simulate" \
  -H "Content-Type: application/json" \
  -d "${PAYLOADS[$SCENARIO]}")

INCIDENT_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('incident_id','unknown'))" 2>/dev/null || echo "unknown")
ok "Incident created: ${AMBER}${INCIDENT_ID}${RESET}"

# 3. Wait for agent to reason
step "Waiting for agent to reason (up to 30s)..."
TIMEOUT=30
ELAPSED=0
while [[ $ELAPSED -lt $TIMEOUT ]]; do
  INCIDENT=$(curl -sf "${COLLECTOR_URL}/incidents/${INCIDENT_ID}" 2>/dev/null || echo "{}")
  STATUS=$(echo "$INCIDENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  if [[ "$STATUS" == "in_triage" || "$STATUS" == "remediating" || "$STATUS" == "resolved" ]]; then
    break
  fi
  printf "."
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done
echo ""

# 4. Print result
INCIDENT=$(curl -sf "${COLLECTOR_URL}/incidents/${INCIDENT_ID}" 2>/dev/null || echo "{}")

ROOT_CAUSE=$(echo "$INCIDENT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('probable_root_cause','(not yet available)')[:200])" 2>/dev/null || echo "")
CONFIDENCE=$(echo "$INCIDENT" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('confidence_score'); print(f'{round(c*100)}%' if c else 'n/a')" 2>/dev/null || echo "n/a")
ACTION=$(echo "$INCIDENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('recommended_action','n/a'))" 2>/dev/null || echo "n/a")
APPROVAL=$(echo "$INCIDENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('requires_approval', True))" 2>/dev/null || echo "True")
STATUS=$(echo "$INCIDENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

echo ""
echo -e "${AMBER}${BOLD}━━━ INCIDENT ANALYSIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Incident ID:     ${AMBER}${INCIDENT_ID}${RESET}"
echo -e "  Status:          ${GREEN}${STATUS}${RESET}"
echo -e "  Confidence:      ${GREEN}${CONFIDENCE}${RESET}"
echo -e "  Recommended:     ${CYAN}${ACTION}${RESET}"
echo -e "  Needs approval:  ${APPROVAL}"
echo -e ""
echo -e "  Root cause:"
echo -e "  ${ROOT_CAUSE}"
echo -e "${AMBER}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

echo ""
ok "Demo complete!"
info "Dashboard:  http://localhost:3001"
info "Incident:   http://localhost:3001/incident/${INCIDENT_ID}"
info "Audit log:  ${COLLECTOR_URL}/incidents/${INCIDENT_ID}/audit"
