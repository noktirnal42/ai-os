#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
AIOS_ROOT="$tmp" python3 "$base/jobs.py" start /bin/sh -c 'printf JOB_OK; sleep 1' > "$tmp/id"
id=$(cat "$tmp/id")
AIOS_ROOT="$tmp" python3 "$base/jobs.py" list | grep "$id"
AIOS_ROOT="$tmp" python3 "$base/jobs.py" log "$id" | grep JOB_OK
printf 'JOBS ALL PASS\n'
