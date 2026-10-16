#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
file="$tmp/notes.txt"
printf '%s\n' one two /o ':d 1' u :wq | python3 "$base/aed.py" "$file" > "$tmp/out"
grep -q '1:one' "$tmp/out"
grep -qx one "$file"
grep -qx two "$file"
printf '%s\n' alpha :wq | python3 "$base/aed.py" "$tmp/new.txt" >/dev/null
grep -q '^alpha$' "$tmp/new.txt"
echo 'AED ALL PASS'
