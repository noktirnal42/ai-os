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

App registration is manifest-backed: installs require a name, version, `/ai`
entry and test path, and an explicit green-test result. The registry tool also
limits mutation volume per session so a model cannot flood the app database.

The first Phase 2 capability is deliberately read-only: `net status` records
structured interface and route observations in `/ai/state/net.json` with an
`emulated` marker. It does not configure interfaces or enable network commands.

The bounded `net` app adds `a-fetch`, which requires the explicit
`AIOS_ALLOW_NETWORK=1` operator gate and an `AIOS_FETCH_ALLOWLIST` host allowlist.
It accepts only HTTP(S), rejects embedded credentials, caps responses at 64 KiB,
and limits requests to ten seconds.

The first Phase 1 application is `apps/calc`. Its acceptance command is
`/ai/apps/calc/tests/run.sh`; a successful build installs `/ai/bin/calc` and
`calc "2^10"` prints `1024`.
