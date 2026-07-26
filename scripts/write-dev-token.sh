#!/usr/bin/env bash
# Writes the collector token where the local Alertmanager expects to read it.
#
# Alertmanager reads the credential from a file rather than from its config, so
# that overriding COLLECTOR_API_TOKEN changes both sides. Without this the
# committed default would go stale on the first override and ingestion would
# fail with a 401 that looks, from the dashboard, exactly like a quiet cluster.
set -euo pipefail
TOKEN="${COLLECTOR_API_TOKEN:-dev-collector-token}"
DEST="$(dirname "$0")/../infra/manifests/collector-token"
printf '%s' "$TOKEN" > "$DEST"
echo "Wrote collector token to $DEST"
