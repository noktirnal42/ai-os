#!/bin/sh
# notes: a tiny note store. Usage: notes add TEXT | list | search WORD
set -eu
FILE="${NOTES_FILE:-/ai/state/notes.txt}"
mkdir -p "$(dirname "$FILE")"
touch "$FILE"
case "${1:-}" in
  add)
    shift
    [ $# -gt 0 ] || { echo "usage: notes add TEXT" >&2; exit 2; }
    printf '%s\n' "$*" >> "$FILE"
    echo "saved"
    ;;
  list)
    awk '{ printf "%3d  %s\n", NR, $0 }' "$FILE"
    ;;
  search)
    shift
    [ $# -gt 0 ] || { echo "usage: notes search WORD" >&2; exit 2; }
    grep -n -i -- "$1" "$FILE" || true
    ;;
  *)
    echo "usage: notes add TEXT | list | search WORD" >&2
    exit 2
    ;;
esac
