.PHONY: test calc-test fileutils-test jobs-test aed-test ask-test eval sandbox-probes

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

eval:
	./evals/run.sh --phase 1 --repeat 1

sandbox-probes:
	AIOS_ROOT=$${AIOS_ROOT:-/tmp/aios-probes} python3 evals/sandbox-probes.py
