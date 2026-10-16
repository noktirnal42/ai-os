.PHONY: selftest test calc-test fileutils-test jobs-test aed-test ask-test net-test eval sandbox-probes live-model-test live-self-build-test live-app-build-test net-probe

selftest:
	./selftest

test:
	python3 -m unittest discover -s tests -v

calc-test:
	./apps/calc/tests/run.sh

fileutils-test:
	./apps/fileutils/tests/run.sh

jobs-test:
	./apps/jobs/tests/run.sh

aed-test:
	./apps/aed/tests/run.sh

ask-test:
	./apps/ask/tests/run.sh

net-test:
	./apps/net/tests/run.sh

eval:
	./evals/run.sh --phase 1 --repeat 1

sandbox-probes:
	AIOS_ROOT=$${AIOS_ROOT:-/tmp/aios-probes} python3 evals/sandbox-probes.py

live-model-test:
	./evals/live-model.sh

live-self-build-test:
	python3 evals/live-self-build.py

live-app-build-test:
	python3 evals/live-app-build.py

net-probe:
	python3 evals/net-probe.py
