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

## Phase 3 G3-2: live network-kill and bridge persistence (2026-10-18)

* cloudbridge now survives VM restarts: /etc/local.d/cloudbridge.start is
  registered in the OpenRC `local` runlevel; after a full `vm.sh stop/boot`
  cycle the bridge answered /healthz with no manual start and completed a
  harness session through it.
* A live network-kill test exposed a real robustness flaw the hermetic suite
  missed: with packets silently dropped (iptables DROP, not refused), a
  request arriving inside the 30-second probe-cache window stalled on the
  full cloud timeout (120s) before falling back — the "no 60s hang" the spec
  forbids. The existing mocks modeled refused connections, which fail
  instantly, not black-holed ones.
* AI OS fixed it itself (cloudbridge v2, verified session): a 3-second TCP
  pre-check before every cloud forward (logging route "probe_failed"),
  probe-cache invalidation after any cloud failure, and two new tests — a
  black-hole server (accepts, never responds) asserting local fallback
  under 5s, and a cache-invalidation test asserting the next request routes
  local with no cloud delay. Suite grew 12 -> 14, all passing.
* Live G3-2 evidence with the full kill (iptables allowed only 10.0.2.2 and
  loopback): harness session completed via local in 4 seconds total
  (bridge log route local, 4402ms), no hang; after removing the rules and
  letting the 30-second probe cache expire, the next request routed cloud,
  status 200 in 2.2s. Both directions evidenced in /ai/state/bridge.log.
* Operator tuning: cloud timeout_s lowered 120 -> 45 as defense in depth.

## Phase 3 G3-4: offline re-test of Phase 0-1 (2026-10-18)

* Live network-down test inside the guest: iptables + ip6tables OUTPUT rules
  allowed only the established SSH console and loopback, dropping all new
  outbound connections on both protocol stacks (the first attempt blocked
  IPv4 only and the suite leaked through IPv6 — guest DNS resolves AAAA
  first and slirp passes IPv6; both tables must be filtered).
* With the network fully down: calc, fileutils, jobs, aed, ask, and net all
  passed their acceptance suites offline; the harness offline smoke
  returned the expected [offline] model disabled response; and the probe
  app correctly detected the outage (DNS_FAIL HTTP_FAIL HTTPS_FAIL
  LINK_DOWN, exit 1) — a live cross-check of G2-3, not a unit test.
* After removing the rules: DNS recovered and the next bridge request
  routed cloud, status 200, in ~2s. Phase 3 gate G3-4 is evidenced.

## Phase 4 begins: task engine F4-1 (2026-10-18)

* AI OS built the tasks CLI autonomously in a verified session run in a
  visible macOS Terminal window (the operator watched the live reasoning
  and tool stream): /ai/bin/tasks with add/list/next/done/fail/show,
  state in /ai/state/tasks.json (overridable via AIOS_TASKS_FILE for
  hermetic tests), integer ids, depends gating in next, fail-closed JSON
  handling. Registered as tasks 0.1.0, tests_pass true.
* Functional check: add two tasks (second depends on the first); next
  correctly returns the first until it is done, then the second. Depends
  gating verified.
* Harness session-resume integration (the doc 07 §8 acceptance) is now
  evidenced — F4-1 is complete. Details below.

## Phase 4 F4-1 acceptance: session resume (2026-10-18)

* Harness (ai/aios.py) now reads the shared task list for state-summary
  injection (doc 05 §7.1): each turn the session refreshes the task-list
  block in the opening user message only when /ai/state/tasks.json changed
  (keeping the prompt-cache prefix stable), and emits a task_state_refresh
  audit event on change. Reading is fail-closed (corrupt/missing JSON reads
  as an empty list) and honors AIOS_TASKS_FILE for hermetic tests.
* New `aios resume [--from SID] [goal]` continues an interrupted session:
  it rebuilds the brief from the unfinished (pending/active/failed) tasks —
  ids, dependency order, acceptance commands — and, with --from, recovers
  the original goal from the killed session's audit log
  (/ai/state/sessions/SID.jsonl). session_start records `resumes: SID`.
  With nothing unfinished it reports "nothing to resume" and exits 0.
* Four new hermetic unit tests (24 total, green in guest and on host):
  fail-closed summary + AIOS_TASKS_FILE override, resume brief content and
  all-done case, run-loop injection + refresh-on-change + resumes field,
  and goal recovery from the audit log (with path-traversal rejection).
* Live acceptance (local model Qwen2.5-7B via host Ollama, guest endpoint
  10.0.2.2:11434): seeded two dependent tasks (step1.txt "ready", step2.txt
  "done" depends on 1), started `aios run`, SIGKILLed the session the moment
  step1's file appeared (work done, task 1 not yet accepted/marked, task 2
  untouched), then ran `aios resume --from <killed sid>`. The resumed
  session: read the existing step1 work and marked task 1 done, created
  step2.txt, ran its acceptance command (exit 0), marked task 2 done, and
  finished. Both task_state_refresh events and every /ai/bin/tasks call are
  in the audit log (20261018T213007Z-afb50ee0.jsonl, resumes=
  20261018T212941Z-c562793f). Final state: both tasks done, both files
  correct.
* One iteration was needed on the resume brief wording: telling the model
  `tasks done <id>` made it try a PATH-less `tasks` (exit 127) and give up
  marking done; the brief now names the absolute path /ai/bin/tasks and
  says to verify interrupted work on disk instead of redoing it.
* Next Phase 4 item: selftest (F4-4).

## Phase 4 F4-3: package export/install (`aipkg`) — complete (2026-10-18)

* New app `aipkg` (ai/apps/aipkg, entry /ai/bin/aipkg, manifest 0.1.0) implementing doc 07 §10:
  `aipkg export NAME... → /ai/out/NAME-<ver>.aipkg` (tarball: manifest.json, registry.json (the
  app's registry entry, or {} when unregistered), entry (deployable copy of the manifest entry
  point; generated as a `#!/bin/sh exec python3` wrapper for Python apps when /ai/bin/<name>
  is absent), src/ (a src/ directory plus root-level .py files), tests/ (when present)) and
  `aipkg install FILE → unpack tarball, run tests/run.sh, register in
  /ai/state/registry.json with tests_pass=true and create the /ai/bin entry point. Failing
  tests abort the install and leave nothing behind (no app dir, no registry entry).
* 12 hermetic unit tests (ai/apps/aipkg/tests/test_aipkg.py): tarball contents (manifest,
  registry, entry, src/, tests/), unregistered-app registry entry, multiple apps, missing
  app/manifest errors, no-args usage (exit 2); install: unpack + test + register, entry
  deployed executable, failing-tests abort + cleanup, missing manifest, missing tests/run.sh,
  nonexistent package, reinstall overwrite. Green: 12/12 on the guest and on the host.
* Live acceptance (AC-5, machine-2 simulation on the guest VM): exported wbrowse
  (0.1.0) to /ai/out/wbrowse-0.1.0.aipkg; stripped the app entirely (app dir, /ai/bin/wbrowse,
  registry entry); installed from the tarball — it unpacked, ran wbrowse's 23 acceptance tests
  (all passed), registered with tests_pass=true, and created executable /ai/bin/wbrowse;
  `wbrowse --dump http://example.com/` renders live (rc=0) and tests/run.sh executes directly
  (exec bit preserved through the tar).
* libhttp prerequisite (fixed earlier, guest-only source patch): /ai/bin/libhttp did not follow
  redirects although the source intended to (the Location value runs to end of header block, so
  strstr(loc, "\\r\\n") returned NULL, and relative locations lack a scheme for parse_url).
  Fixed ai/apps/libhttp/libhttp.c (capture value to end of buffer; resolve scheme-less locations
  against the current host) and rebuilt/reinstalled /ai/bin/libhttp. Verified relative, absolute
  and chained redirects plus a 404. ai/apps/libhttp does not exist in the host checkout, so that
  source patch and rebuilt binary live in the guest; add them to the host tree before the next
  commit cycle.
* Remaining: `aios registry install wbrowse` requires the registry's human TTY approval
  (ask_human) — not reachable through vm.sh exec. Run it interactively (see command below),
  which also runs the app tests with the harness gate.

## Phase 4 F4-3: package export/install (`aipkg`) — complete (2026-10-18)

* New app `aipkg` (ai/apps/aipkg, entry /ai/bin/aipkg, manifest 0.1.0) implementing doc 07 §10:
  `aipkg export NAME... → /ai/out/NAME-<ver>.aipkg` (tarball: manifest.json, registry.json (the
  app's registry entry, or {} when unregistered), entry (deployable copy of the manifest entry
  point; auto-generated as a `#!/bin/sh exec python3` wrapper for Python apps when no
  /ai/bin/<name> exists), src/ (a src/ directory plus root-level .py files), tests/ (when
  present)) and `aipkg install FILE → unpack tarball, run tests/run.sh in a sandbox, register
  in /ai/state/registry.json with tests_pass=true, and create the /ai/bin entry point. Failing
  tests abort the install and leave nothing behind (no app dir, no registry entry).
* 12 hermetic unit tests (ai/apps/aipkg/tests/test_aipkg.py): tarball contents, unregistered-app
  registry entry, multiple apps, missing app/manifest errors, no-args usage (exit 2); install:
  unpack + test + register, entry deployed executable, failing-tests abort + cleanup, missing
  manifest, missing tests/run.sh, nonexistent package, reinstall overwrite. Green: 12/12 on the
  guest and on the host.
* Live acceptance (AC-5, machine-2 simulation on the guest VM): exported wbrowse (0.1.0) to
  /ai/out/wbrowse-0.1.0.aipkg (self-contained: src/wbrowse.py + tests + manifest + registry
  entry + generated entry wrapper); stripped the app entirely (app dir, /ai/bin/wbrowse,
  registry entry); installed fresh from the tarball — it unpacked, ran wbrowse's 23 acceptance
  tests (all passed), registered with tests_pass=true, created executable /ai/bin/wbrowse;
  `wbrowse --dump http://example.com/` renders live through the installed entry (rc=0).
* Registration: `aios registry install wbrowse` requires the registry's human TTY approval
  (ask_human) — not reachable through vm.sh exec; run it interactively.
* Remaining: selftest (F4-4).

## Phase 4 F4-4: selftest — complete (2026-10-18)

* New app `selftest` (ai/apps/selftest, entry /ai/bin/selftest, manifest 0.1.0) implementing
  doc 07 §11: reads /ai/state/registry.json, runs every registered app's tests/run.sh in a
  sandboxed subprocess (AIOS_ALLOW_NETWORK, AIOS_MODEL_URL and AIOS_MODEL stripped from the
  environment; 300s per-app timeout), prints a name/pass/secs table, exits 0 iff all pass, and
  writes /ai/state/selftest-<ts>.json with the full report.
* 7 hermetic unit tests (ai/apps/selftest/tests/test_selftest.py): all-pass registry, single
  failure, missing tests/run.sh entry, empty registry, missing registry file, sandbox env
  stripping, per-app timeout. Green: 7/7 on the guest and on the host.
* Harness gate: `aios run --require-selftest` refuses to run (exit 3) when no selftest report
  exists or the latest report is not all_pass; a green report lets the session proceed. Live
  acceptance: no report → rc 3; after `selftest` writes a green report, `aios run --offline
  --require-selftest` proceeds to the session (offline model, rc 0).
* Next Phase 5 item: long-horizon autonomy / harness self-modification review board.

## Phase 4 F4-2: text browser (`wbrowse`) — complete (2026-10-18)

* New app `wbrowse` (ai/apps/wbrowse, entry /ai/bin/wbrowse, manifest 0.1.0) implementing doc 07 §9: libhttp fetch
  (`/ai/bin/libhttp`, env override AIOS_LIBHTTP) -> minimal stdlib HTML parser (headings, lists, paragraphs, pre passthrough,
  scripts/styles dropped, entities decoded, numbered links [N]) -> line-wrapped renderer -> curses viewer with keys
  j/k scroll, Tab next link, Enter open link under cursor, b back, q quit, :open URL; plus --dump / --html-file
  non-interactive modes for tests and acceptance.
* 23 tests (ai/apps/wbrowse/tests/test_wbrowse.py): fixture HTMLs (headings, lists, links, nested inline tags,
  entities &#233;/&lt;/&amp;/&quot;, pre blocks, script/style suppression, br, empty anchors, link marker spans, width
  wrapping), relative-link resolution, history stack push/back/truncation, redirect following through libhttp against a
  loopback server (relative, absolute, chained), 404 error page, dump-mode exit codes. Green: 23/23 on the guest
  (fetch tests hit the real libhttp); host runs 20/23 with the 3 fetch tests skipped (no /ai/bin/libhttp on host).
* Acceptance: `wbrowse --html-file tests/fixtures/sample.html` renders headings, bullets, verbatim pre, entities and
  numbered links rc=0; `wbrowse --dump http://example.com/` renders live (rc=0); interactive curses viewer smoke-tested
  via pty (starts, draws, quits on q).
* libhttp prerequisite: /ai/bin/libhttp did not follow redirects although the source intended to (the Location value
  runs to the end of the header block, so strstr(loc, "\\r\\n") returned NULL, and relative locations lack a scheme for
  parse_url). Fixed ai/apps/libhttp/libhttp.c (capture value to end of buffer; resolve scheme-less locations against
  the current host) and rebuilt/reinstalled /ai/bin/libhttp. Verified relative, absolute and chained redirects plus a
  404. Guest-only change: ai/apps/libhttp does not exist in the host checkout, so the source patch and rebuilt binary
  live in the guest; add them to the host tree before the next commit cycle.
* Remaining: `aios registry install wbrowse` requires the registry's human TTY approval (ask_human) — not reachable
  through vm.sh exec. Run it interactively (see command below), which also runs the app tests with the harness gate.
