#!/bin/sh
# Acceptance test for a staged module, run against its built .ko. It does not load the module.
# It checks the module's identity and that it was built against the running kernel.
set -eu
KO="$1"
NAME=$(basename "$KO" .ko)
[ "$(modinfo -F name "$KO")" = "$NAME" ] || { echo "module name does not match file name"; exit 1; }
[ "$(modinfo -F license "$KO")" = "GPL" ] || { echo "license must be GPL"; exit 1; }
[ "$(modinfo -F vermagic "$KO" | cut -d' ' -f1)" = "$(uname -r)" ] || { echo "vermagic does not match the running kernel"; exit 1; }
strings "$KO" | grep -q "aios_hello: loaded" || { echo "expected load message not found"; exit 1; }
echo KSTAGE_TEST_PASS
