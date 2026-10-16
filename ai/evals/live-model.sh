#!/bin/sh
set -eu

url=${AIOS_MODEL_URL:-}
model=${AIOS_MODEL:-}
[ -n "$url" ] || { echo "AIOS_MODEL_URL is required" >&2; exit 2; }
[ -n "$model" ] || { echo "AIOS_MODEL is required" >&2; exit 2; }

root=${AIOS_ROOT:-/ai}
probe="$root/tmp/live-model-smoke.txt"
rm -f "$probe"

answer=$(AIOS_MODEL_URL="$url" AIOS_MODEL="$model" /ai/bin/aios ask \
  'Reply with exactly LIVE_MODEL_OK')
[ "$answer" = "LIVE_MODEL_OK" ] || { echo "unexpected model answer: $answer" >&2; exit 1; }

AIOS_MODEL_URL="$url" AIOS_MODEL="$model" /ai/bin/aios run --max-tools 4 --max-seconds 120 \
  "Use fs_write to create $probe with exactly LIVE_TOOL_OK, then stop." >/dev/null
[ "$(cat "$probe")" = "LIVE_TOOL_OK" ] || { echo "model tool mutation failed" >&2; exit 1; }
echo "live model smoke: PASS ($model via $url)"
