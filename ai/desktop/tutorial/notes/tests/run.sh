#!/bin/sh
# Acceptance test for notes. Uses a private file so the real notes are untouched.
set -eu
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
export NOTES_FILE="$W/notes.txt"
N=/ai/bin/notes

$N add "buy milk" >/dev/null
$N add "call the dentist" >/dev/null

COUNT=$($N list | wc -l | tr -d ' ')
[ "$COUNT" = "2" ] || { echo "list count failed: $COUNT"; exit 1; }

$N search dentist | grep -q "call the dentist" || { echo "search failed"; exit 1; }
[ -z "$($N search zebra)" ] || { echo "search for a missing word should print nothing"; exit 1; }

if $N add >/dev/null 2>&1; then
  echo "add without text should fail"
  exit 1
fi

echo NOTES_ALL_PASS
