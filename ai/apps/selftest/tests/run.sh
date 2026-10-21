#!/bin/sh
# selftest acceptance test runner (doc 07 §11, F4-4).
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
python3 "$ROOT/apps/selftest/tests/test_selftest.py"
echo SELFTEST_ALL_PASS
