#!/bin/sh
# aipkg acceptance test runner (doc 07 §10, F4-3).
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
python3 "$ROOT/apps/aipkg/tests/test_aipkg.py"
echo AIPKG_ALL_PASS
