#!/bin/zsh
# Non-destructive platform smoke check, using only vm.sh; VM must already be ready.
set -euo pipefail
EM_DIR="${${(%):-%N}:A:h:h}"
VM="$EM_DIR/vm.sh"
tmp="$(mktemp -d -t aios-emulation-smoke)"
trap 'rm -rf "$tmp"' EXIT
"$VM" exec 'test "$(uname -m)" = aarch64 && test -f /ai/.provisioned && sudo -n true && test -w /ai/tmp'
"$VM" push "$EM_DIR/tests/smoke.c" /ai/tmp/emulation-smoke.c
"$VM" exec 'cc -Wall -Wextra -Werror /ai/tmp/emulation-smoke.c -o /ai/tmp/emulation-smoke && /ai/tmp/emulation-smoke'
"$VM" pull /ai/tmp/emulation-smoke.c "$tmp/pulled.c"
cmp "$EM_DIR/tests/smoke.c" "$tmp/pulled.c"
code=0
"$VM" exec 'exit 37' || code=$?
[[ "$code" == 37 ]] || { print -u2 "exit propagation failed: $code"; exit 1; }
print 'platform smoke: architecture, sudo, compile/run, push/pull, exit propagation PASS'
