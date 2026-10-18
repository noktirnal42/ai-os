# AI OS bootstrap validation — 2026-10-16

The first AI OS slice was built and tested inside the validated Alpine aarch64
emulator. This is a Python reference harness plus the first Phase 1 utilities.

Guest evidence:

* `make test`: 20 harness tests pass, including TUI input/progress/config coverage
  for the documented and observed local-model formats and registry budget
  coverage after multi-step builds.
* `make calc-test`: calculator acceptance passed with `ALL PASS` under Alpine GCC.
* `calc "2^10"`: printed `1024`.
* `make fileutils-test`: file utilities acceptance passed with `FILEUTILS ALL PASS`.
* `make jobs-test`: job runner start/list/log/kill acceptance passed.
* `make aed-test`: line editor save, search, delete, undo, and quit acceptance passed.
* `make ask-test`: offline `ask` command acceptance passed.
* Interactive calculator input `x = 5`, `x * 2`, `quit` returned `10`.
* `/ai/bin/aios run --offline "run the offline bootstrap smoke"`: returned the
  explicit `[offline] model disabled` response and wrote a JSONL verdict under
  `/ai/state/sessions/`.
* Registry installs were performed through the harness registry tool. `/ai/state/registry.json`
  contains `calc`, `fileutils`, `jobs`, `aed`, and `ask`, each with `tests_pass: true`
  and manifest paths.
* Registry hardening rejects incomplete manifests, mismatched names, non-`/ai`
  entry/test paths, failed tests, unsafe app names, and sessions over the
  registry operation budget.
* Registry install reads the manifest from the app workspace, requests human
  approval before test execution, runs the fixed acceptance script with network
  disabled, and registers only a successful result.
* Live self-build trial (Alpine guest, Ollama `qwen2.5-coder:3b` via
  `http://10.0.2.2:11434`): AI OS used `fs_write` to create the `hello-self`
  C source, acceptance script, and manifest. The guest compiled it with
  `gcc -Wall -Wextra -Werror`; the test printed `HELLO_SELF_PASS`, and the app
  printed `HELLO_FROM_AI_OS`. AI OS requested `registry install`, the human gate
  was approved, and the harness acceptance run passed with `tests_pass: true`.
  This trial needed several focused prompts after the first build attempt
  stopped with incomplete files; autonomous long-horizon completion is still
  unproven.
* Follow-up build-loop evaluation: text-only JSON responses with multiple tool
  requests are now handled one request at a time, and the registry rate limit
  counts registry calls rather than all build tools. In the guest, Qwen generated
  `hello-loop2` source and manifest and compiled the binary. Its generated
  acceptance scripts were defective, so the operator replaced the test with a
  fail-closed POSIX script and verified `HELLO_LOOP2_PASS`. AI OS then requested
  `registry install`; the human approved the displayed entry/test summary, the
  installer reran the acceptance test successfully, and the registry records
  `tests_pass: true`. This verifies the install loop after an operator test fix;
  autonomous acceptance-test authoring remains an open limitation.
* Repeatable live self-build eval (`qwen2.5-coder:3b`, Alpine aarch64 guest):
  after the harness added explicit required compiler/test commands, bounded
  continuation on early final responses, duplicate-call feedback, and a narrow
  in-workspace `/bin/sh` fallback, three consecutive runs passed. In each run
  AI OS wrote the source, acceptance script, and manifest, compiled the guest
  ELF, and ran the acceptance test; the harness logged verified success for
  both required commands. Independent checks confirmed exact app output, a
  passing positive test, rejection of a deliberately bad binary, and restoration
  of the original binary. No install or registry operation was requested.
  A Qwen 2.5 Coder 7B cross-check compiled the app and passed independent
  acceptance, but did not call its required test command through the harness;
  it correctly scored false. Qwen 7B autonomous completion remains unproven.
  Per-run JSONL evidence is in `/ai/state/evals/live-self-build.jsonl`.
* New-app build eval: AI OS generated a streaming C line counter, compiler
  command, acceptance test, and manifest. The first build missed the empty
  input case; a bounded Qwen 7B repair wrote the `saw_input` correction, and a
  subsequent AI OS verification session compiled the repaired source and ran
  its acceptance test with a verified-success verdict. The evaluator's
  `--score-existing <app-name>` mode combines sessions tied to the app and
  independently reruns seven resource-limited hidden cases. All seven passed:
  empty input, one line, unterminated final line, blank lines, mixed lines, 512
  lines, and a 64 KiB line. The exact acceptance script passed, rejected a
  deliberately bad binary, and passed again after binary restoration. This is
  a verified generated-app pass after a repair cycle, not a claim of one-shot
  completion. Evidence is in `/ai/state/evals/live-app-build.jsonl`.
* The read-only Phase 2 network probe records `/ai/state/net.json` with schema
  version, interface/route observations, and `emulated: true`; it performs no
  interface mutation or external fetch.
* `apps/net/tests/run.sh` passes the operator network gate and host allowlist
  checks, then verifies bounded local HTTP fetch, DNS resolution, HTTP HEAD
  status, and rejection of redirects to hosts outside the allowlist; denied
  requests remain denied when either control is absent.
* `make selftest` runs the full harness, app, and network observation acceptance
  suite. On hosts
  without Linux `ip`, it marks the guest-only interface probe as skipped; the
  Alpine guest runs it and verifies two interfaces and two routes.
* The harness fake-model test drove a real `fs_write` tool call, verified the file
  mutation, then completed the session with an assistant message.
* Live inference through the host Ollama OpenAI-compatible endpoint succeeded:
  `AIOS_MODEL_URL=http://10.0.2.2:11434 AIOS_MODEL=qwen2.5-coder:3b /ai/bin/aios ask
  "Reply with exactly LIVE_MODEL_OK"` returned `LIVE_MODEL_OK`.
* The same live model generated a JSON tool call which the harness parsed and
  executed. `/ai/tmp/live-model-two.txt` contained `LIVE_TWO_TOOL_OK`, and the
  session JSONL recorded successful `fs_write` and `shell` tool results.
* `evals/live-model.sh` now packages those two checks as a repeatable guest
  smoke test using explicit `AIOS_MODEL_URL` and `AIOS_MODEL` overrides.
* `evals/run.sh --phase 1 --repeat 2` passed all six Phase 1 tasks twice and
  appended the results to `/ai/state/evals.csv`.
* `evals/sandbox-probes.py` passed secret, protected-path, network, and shadow-file
  denial probes. Phase 0/1 shell networking is disabled unless explicitly enabled
  in the process environment.

The harness enforces `/ai` path policy, rejects `/ai/secrets`, caps shell output at
4 KiB, bounds shell timeouts, rejects a Phase 0 destructive-command subset, keeps
session logs append-only JSONL, and implements checkpoint and registry tools. Its
model client speaks the OpenAI-compatible `/v1/chat/completions` endpoint exposed
by the planned host model server.

The VM was checkpointed as `phase1-foundation-apps-v2` before this slice. The
next checkpoint is taken after the evaluation and probe suite and becomes the
current Phase 1 baseline. Resume with:

```sh
emulation/vm.sh boot && emulation/vm.sh wait
emulation/vm.sh exec '/ai/bin/calc "2^10"'
```

The default endpoint remains `http://10.0.2.2:8080` for the planned dedicated
model host and is intentionally optional. The current live test path uses the
host Ollama service at `http://10.0.2.2:11434` with `qwen2.5-coder:3b`; the endpoint
and model are process overrides, so the guest default configuration is unchanged.
The harness accepts both native OpenAI `tool_calls` and the fenced JSON tool-call
format emitted by this model. Model behavior is still bounded by the session's
tool and time budgets; a model can emit an invalid follow-up tool request, which
is logged as a tool error without escaping the workspace policy.

## Beginner console update — 2026-10-16

* `./emulation/start.sh` detected host Ollama, selected the installed
  `qwen2.5-coder:3b`, wrote `/ai/state/model.json`, synced the console into the
  running Alpine guest, and opened the TUI.
* TUI Chat mode returned exactly `AIOS_CHAT_OK`. First response took about one
  minute while Ollama loaded the model; elapsed time was visible. The default
  model request limit is now 300 seconds (configurable from 10 to 600).
* TUI Do mode invoked a shell tool, printed `AIOS_DO_FINAL_OK`, and displayed
  normalized arguments, command start, and exit status 0. The harness marked the
  no-acceptance-command session partial, and the UI accurately said the tool ran
  but task completion was not verified.
* The live run exposed and fixed two curses input bugs (text keycodes and Enter
  representation), a short-model nested shell-argument shape, and fast-session
  audit events being missed at process exit.
* Host verification: 20 harness tests, `make -C ai selftest`, Phase 1 eval,
  emulator push/build/run/exit-propagation smoke test, shell syntax checks, and
  marketing HTML/SVG parse all passed. `vm.sh status` reports Ollama reachable.
* The VM remains running so the user's existing and new Terminal sessions are
  available. No snapshot was taken because the VM checkpoint workflow requires
  stopping the guest.

## Cloud providers, streaming console, and the verified self-build loop (2026-10-18)

* Cloud model configuration: `emulation/sync-keys.sh` copied the operator's
  OpenRouter, Ollama Cloud, and NVIDIA NIM keys from the macOS Keychain into
  `/ai/secrets/*.key` (0600, key material never printed; one transient
  keychain-lock race was found and the script now retries). The harness reads
  the key from `AIOS_MODEL_KEY` or `AIOS_MODEL_KEY_FILE` and sends
  `Authorization: Bearer` only when a key exists, so local endpoints are
  unaffected.
* Live endpoints verified from inside the guest: OpenRouter `openrouter/free`
  (capable but rate-limited 429 under agent loops), Ollama Cloud
  `gemma4:31b-cloud` (reliable — used as the self-build workhorse), NVIDIA NIM
  `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` and
  `meta/llama-3.2-90b-vision-instruct` (periodic 503 ResourceExhausted).
  `meta/codellama-70b` and several older NIM slugs 404 for this account.
* Harness robustness: model responses stream over SSE with `reasoning_content`
  separated from `content` (NVIDIA reasoning models previously looked silent),
  streamed native `tool_calls` fragments are reconstructed by index, in-stream
  `error` chunks raise instead of silently producing nothing, 429/5xx retry
  with backoff, and malformed tool-call JSON no longer crashes the session.
* `--require-command` crediting now matches a required command contained in a
  batched successful shell call. Previously, models that ran two required
  commands in one invocation were never credited and every such session was
  mislabeled partial despite passing verifications.
* Autonomous app builds (each registered with `tests_pass: true`, operator
  gate approved, host suite green after pull): `libhttp` (F2-3) — 188-line C
  HTTP/1.1 client, compiles `-Wall -Wextra -Werror`, live-verified fetching
  `http://example.com` body with status 200 after AI OS fixed its own
  status-parsing bug (printed 0 instead of 200); `net` (F2-4) — `a-fetch` and
  `a-ping` CLIs with acceptance tests.
* `probe` app built autonomously by AI OS and registered with
  `tests_pass: true`; live output `DNS_OK HTTP_OK ROUTE_OK LINK_OK` exit 0.
  This provides evidence for G2-2 (net.json matches `ip route`) and G2-3
  (link-loss detection). G2-1 is satisfied in reduced scope: the live probe
  targets `http://example.com` because libhttp does not implement TLS yet;
  the spec's HTTPS probe remains open pending mbedtls/libtls integration
  (openssl-dev is installed in the guest).
* Six TUI features were built by AI OS itself through the verified Do-mode
  loop (one shell-verification script per task, `verdict: succeeded,
  verified: true`): up-arrow history recall, `/clear` + `/history`,
  persistent history in `/ai/state/history.json`, tab completion of slash
  commands, `/status` + `/retry`, and `/run` (a staged shell command with
  `/ok` confirmation — proposed by AI OS when asked what to improve next).
  Each was pulled from the guest and re-verified against the 20-test host
  suite before integration; a guest-side `/ai/tmp/verify_tui.sh` +
  `verify_extra.sh` pattern replaced inline quoting-fragile
  `--require-command` strings.
* `start.sh` no longer overwrites `/ai/state/model.json` when a selection
  already exists (a restart previously reverted the operator's F3 provider
  choice to the local 3B model). Evidence: `emulation/start.sh` guard and
  live re-check after snapshot restore.
* Milestone snapshot: `phase2-selfbuild` (2026-10-18, after the six
  self-improvements and the Phase 2 app builds; commit fcb47ab).

## TLS in libhttp and full G2-1 (2026-10-18)

* AI OS attempted HTTPS support autonomously (40-tool session, budget
  exhausted mid-task) and produced a structurally correct OpenSSL path that
  failed at runtime. Host-side diagnosis: the code never set SNI, so servers
  answered TLS alert 40 (handshake failure) while curl to the same host
  succeeded. A minimal debug program reproduced the failure independently of
  libhttp, isolating the cause. Fix: SSL_set_tlsext_host_name(ssl, host)
  before SSL_connect.
* After the SNI fix: /ai/bin/libhttp https://example.com and
  https://huggingface.co both return 200 (live, from inside the guest).
  a-fetch was recompiled against the TLS-enabled library (-lssl -lcrypto).
* The model had left tests/run.sh as a bare `exit 0` stub; the operator
  replaced it with a real acceptance test: unit checks compiled
  -Wall -Wextra -Werror with -lssl -lcrypto, live plain-HTTP 200, live HTTPS
  200, and a bad-host rejection check. Output: LIBHTTP_ALL_PASS. libhttp 0.2.0
  was registered through the normal operator gate with these tests passing.
* probe app upgraded: HTTPS_OK check added (a-fetch https://huggingface.co).
  Live output: DNS_OK HTTP_OK HTTPS_OK ROUTE_OK LINK_OK, exit 0. Phase 2 exit
  gates G2-1 (full HTTPS form), G2-2, and G2-3 are all evidenced by this run.

## Phase 3: cloudbridge (2026-10-18)

* AI OS built the cloudbridge daemon autonomously in one verified session
  (gemma4:31b-cloud, 60-tool budget): a stdlib-only OpenAI-compatible router on
  127.0.0.1:8081 with cloud forwarding (key from /ai/secrets, never from the
  client), silent local fallback, 30-second-cached offline-floor probe, JSONL
  bridge log, and a 12-case hermetic unittest suite (mock upstreams on
  ephemeral ports; passthrough, model rewrite, 401/timeout/refused fallback,
  floor fast-path, malformed JSON 400, both-fail 502, key redaction). All 12
  passed in ~9s. Registered as cloudbridge 0.1.0 with tests_pass: true.
* Operator repairs after the build: (1) the floor probe crashed with
  ValueError on cloud URLs without an explicit port — the hermetic test
  doubles all used mock URLs with ports, which masked the real-world URL
  shape; fixed to rsplit + scheme-default port; (2) the hermetic coverage gap
  is recorded as a lesson, not silently patched in tests.
* Live behavior, evidenced by /ai/state/bridge.log: floor probe passes
  (probe=True, integrate.api.nvidia.com:443), cloud attempt returns NVIDIA
  503 ResourceExhausted, bridge logs {route: cloud, status: 503,
  fallback: true} and silently serves from local Ollama 200 (~1s).
* Phase 3 gate G3-1 satisfied: harness pointed at http://127.0.0.1:8081
  (model.json) completed a live `aios ask` session; log shows the route
  decision (route: cloud, status 200, no fallback on the recorded pass).
  G3-3 (key redaction) is covered by suite case 11; G3-2 live network-kill
  and G3-4 offline-reboot tests remain open.
* Deployment note: the bridge runs via setsid and survives ssh sessions but
  not VM restarts; restart with `setsid python3 -u /ai/apps/cloudbridge/
  cloudbridge.py &`. Rollback: point /ai/state/model.json back at the direct
  provider URL.
