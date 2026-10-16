#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for tool in a-ls a-cat a-cp a-mv a-find a-rm; do cp "$base/bin/$tool" "$tmp/$tool"; chmod +x "$tmp/$tool"; done
mkdir -p "$tmp/tree/sub"; printf 'hello\n' > "$tmp/tree/a.txt"; printf 'world\n' > "$tmp/tree/sub/b.txt"
[ "$("$tmp/a-cat" "$tmp/tree/a.txt")" = hello ]
"$tmp/a-cp" "$tmp/tree/a.txt" "$tmp/tree/c.txt"; [ -f "$tmp/tree/c.txt" ]
"$tmp/a-mv" "$tmp/tree/c.txt" "$tmp/tree/d.txt"; [ -f "$tmp/tree/d.txt" ]
[ "$("$tmp/a-find" "$tmp/tree" -name '*.txt' -type f | wc -l | tr -d ' ')" = 3 ]
[ "$("$tmp/a-ls" "$tmp/tree" | grep -c a.txt)" -eq 1 ]
"$tmp/a-rm" "$tmp/tree/d.txt"; [ ! -e "$tmp/tree/d.txt" ]
if "$tmp/a-rm" / 2>/dev/null; then exit 1; fi
if "$tmp/a-rm" "$tmp/tree" 2>/dev/null; then exit 1; fi
if "$tmp/a-cat" 2>/dev/null; then exit 1; fi
printf 'FILEUTILS ALL PASS\n'
