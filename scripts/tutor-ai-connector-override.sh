#!/usr/bin/env bash
set -euo pipefail

SECRET="${1:-}"
PUBLISH_USERNAME="${2:-admin}"
ALLOWED_HOSTS="${3:-scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn}"

if [[ -z "$SECRET" ]]; then
  echo "Usage: scripts/tutor-ai-connector-override.sh <HMAC_SECRET> [PUBLISH_USERNAME] [ALLOWED_HOSTS]" >&2
  exit 2
fi
if ! command -v tutor >/dev/null 2>&1; then
  echo "tutor command not found. Run this on the Open edX/Tutor server." >&2
  exit 2
fi

ROOT="$(tutor config printroot)"
mkdir -p "$ROOT/env/local"
TARGET="$ROOT/env/local/docker-compose.override.yml"
if [[ -f "$TARGET" ]]; then
  cp "$TARGET" "$TARGET.bak.$(date +%Y%m%d_%H%M%S)"
fi
cat > "$TARGET" <<YAML
services:
  cms:
    environment:
      AI_CONNECTOR_PUBLISH_USERNAME: "$PUBLISH_USERNAME"
      AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH: "false"
      AI_CONNECTOR_HMAC_SECRET: "$SECRET"
      AI_CONNECTOR_HMAC_SKEW_SECONDS: "300"
      AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS: "$ALLOWED_HOSTS"
      AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED: "false"
      AI_CONNECTOR_TAGGING_ENABLED: "true"
      AI_CONNECTOR_TAG_TAXONOMY_EXPORT_ID: "ai-learning-check"
      AI_CONNECTOR_TAG_TAXONOMY_NAME: "AI Learning Check"

  cms-worker:
    environment:
      AI_CONNECTOR_PUBLISH_USERNAME: "$PUBLISH_USERNAME"
      AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH: "false"
      AI_CONNECTOR_HMAC_SECRET: "$SECRET"
      AI_CONNECTOR_HMAC_SKEW_SECONDS: "300"
      AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS: "$ALLOWED_HOSTS"
      AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED: "false"
      AI_CONNECTOR_TAGGING_ENABLED: "true"
      AI_CONNECTOR_TAG_TAXONOMY_EXPORT_ID: "ai-learning-check"
      AI_CONNECTOR_TAG_TAXONOMY_NAME: "AI Learning Check"
YAML

echo "Wrote $TARGET"
echo "Restart with: tutor local restart cms cms-worker"
