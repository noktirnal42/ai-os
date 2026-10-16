#!/bin/sh
set -eu
url=${AIOS_MODEL_URL:-http://10.0.2.2:8080}
if ! curl -fsS "$url/health" >/dev/null 2>&1; then
  # Ollama's OpenAI-compatible surface does not expose /health; its model
  # catalog is the portable readiness check.
  curl -fsS "$url/v1/models" >/dev/null || { echo "model health unavailable: $url" >&2; exit 4; }
fi
curl -fsS "$url/v1/models"
