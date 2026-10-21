#!/bin/sh
# Release manifest for the AI OS guest. Run inside the VM:
#   emulation/vm.sh exec 'sh /ai/release/manifest.sh' ; emulation/vm.sh pull /ai/release/manifest.json ai/release/manifest.json
# Records what this guest is made of: kernel, pinned packages, and hashes of the repo-managed files.
set -eu
OUT="${1:-/ai/release/manifest.json}"
mkdir -p "$(dirname "$OUT")"
{
  echo "{"
  echo "  \"kernel\": \"$(uname -r)\","
  echo "  \"alpine\": \"$(cat /etc/alpine-release)\","
  echo "  \"packages\": ["
  apk info -v 2>/dev/null | sort | sed 's/.*/    "&",/' | sed '$ s/,$//'
  echo "  ],"
  echo "  \"files\": {"
  first=1
  for f in $(find /ai/desktop /ai/bin /ai/apps /ai/kernel/bin /ai/kernel/examples -type f 2>/dev/null | sort); do
    h=$(sha256sum "$f" | cut -d' ' -f1)
    [ $first -eq 1 ] || echo ","
    printf '    "%s": "%s"' "$f" "$h"
    first=0
  done
  echo ""
  echo "  }"
  echo "}"
} > "$OUT"
echo "wrote $OUT"
