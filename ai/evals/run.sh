#!/bin/sh
set -eu
phase=1
repeat=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --phase) phase=$2; shift 2;;
        --repeat) repeat=$2; shift 2;;
        *) echo "usage: run.sh [--phase 1] [--repeat N]" >&2; exit 2;;
    esac
done
[ "$phase" = 1 ] || { echo "only Phase 1 is implemented" >&2; exit 2; }
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ -n "${AIOS_ROOT:-}" ]; then
    root=$AIOS_ROOT
elif [ -d /ai ] && [ -w /ai ]; then
    root=/ai
else
    root="$base/.eval-state"
fi
mkdir -p "$root/state"
csv="$root/state/evals.csv"
[ -e "$csv" ] || printf 'timestamp,phase,task,pass,repeat\n' > "$csv"
run_task() {
    task=$1; command=$2; n=$3
    if sh -c "$command" >/tmp/aios-eval.out 2>/tmp/aios-eval.err; then pass=1; else pass=0; fi
    printf '%s,%s,%s,%s,%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$phase" "$task" "$pass" "$n" >> "$csv"
    [ "$pass" = 1 ] || { cat /tmp/aios-eval.out /tmp/aios-eval.err >&2; return 1; }
}
n=1
while [ "$n" -le "$repeat" ]; do
    run_task harness "cd '$base' && python3 -m unittest discover -s tests -q" "$n"
    run_task calc "cd '$base' && ./apps/calc/tests/run.sh" "$n"
    run_task fileutils "cd '$base' && ./apps/fileutils/tests/run.sh" "$n"
    run_task jobs "cd '$base' && ./apps/jobs/tests/run.sh" "$n"
    run_task aed "cd '$base' && ./apps/aed/tests/run.sh" "$n"
    run_task ask "cd '$base' && ./apps/ask/tests/run.sh" "$n"
    n=$((n + 1))
done
echo "Phase $phase eval PASS ($repeat repetition(s)); results: $csv"
