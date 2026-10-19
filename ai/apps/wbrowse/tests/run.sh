#!/bin/sh
# wbrowse acceptance test runner (doc 07 §9, F4-2).
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
python3 "$ROOT/apps/wbrowse/tests/test_wbrowse.py"
echo WBROWSE_ALL_PASS
