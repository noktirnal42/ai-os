# AI OS bootstrap

This is the first AI OS slice built inside the Alpine aarch64 emulator. It is a
small Python reference harness for Phase 0/1 work; the target C implementation
can replace it later without changing the tool contract.

The harness has three entry points:

* `aios ask "question"` sends one model request without tools.
* `aios run "goal"` starts a bounded tool session.
* `aiosd` runs the same session engine as a foreground daemon-compatible command.

Set `AIOS_MODEL_URL` to an OpenAI-compatible server. A deterministic `--offline`
mode is provided for emulator and regression tests; it never pretends to have
performed model inference.

All session state lives below `/ai/state`. Model writes are restricted to the
documented `/ai` subtrees, `/ai/secrets` is inaccessible, shell commands run
without network access by default, and every tool call/result is appended to a
JSONL session log.

The first Phase 1 application is `apps/calc`. Its acceptance command is
`/ai/apps/calc/tests/run.sh`; a successful build installs `/ai/bin/calc` and
`calc "2^10"` prints `1024`.
