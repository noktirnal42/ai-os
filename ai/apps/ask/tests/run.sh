#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
out=$(AIOS_ROOT="$tmp" python3 "$base/aios.py" ask --offline 'offline smoke')
[ "$out" = '[offline] model disabled' ]
echo 'ASK ALL PASS'
