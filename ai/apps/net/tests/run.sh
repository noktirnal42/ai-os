#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
TMP=$(mktemp -d)
trap 'kill "$SERVER" 2>/dev/null || true; rm -rf "$TMP"' EXIT
printf 'NET_OK\n' > "$TMP/index.html"
python3 -m http.server 18765 --bind 127.0.0.1 --directory "$TMP" >/dev/null 2>&1 &
SERVER=$!
sleep 1
if AIOS_ALLOW_NETWORK=1 AIOS_FETCH_ALLOWLIST=127.0.0.1 "$ROOT/apps/net/bin/a-fetch" http://127.0.0.1:18765/ | grep -qx NET_OK; then :; else
  echo 'network fetch acceptance failed' >&2; exit 1
fi
if "$ROOT/apps/net/bin/a-fetch" http://127.0.0.1:18765/ >/dev/null 2>&1; then
  echo 'network gate failed open' >&2; exit 1
fi
if AIOS_ALLOW_NETWORK=1 AIOS_FETCH_ALLOWLIST=example.com "$ROOT/apps/net/bin/a-fetch" http://127.0.0.1:18765/ >/dev/null 2>&1; then
  echo 'network allowlist failed open' >&2; exit 1
fi
echo 'NET ALL PASS'
