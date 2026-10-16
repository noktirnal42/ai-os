# 07 — Subsystem Development Specs

Each spec is handed to the agent as a session brief (see doc 08 for the prompt
wrapper). Every spec ends in acceptance criteria the harness verifies. IDs map to
doc 01 requirements.

---

## §1 Calculator (`calc`) — F1-1

**Interface:** `/ai/bin/calc "expr"` one-shot; `/ai/bin/calc` interactive REPL
(`> prompt`, `quit`, `help`, `vars`).
**Language:** C (single translation unit + test driver) — teaches the agent C
discipline; alternatives allowed if manifest says so.
**Features:** `+ - * / %` precedence, unary minus, parens, `^` power, functions
`sqrt sin cos tan log log10 exp abs floor ceil pow`, constants `pi e`, variables
(`x = 5` then use), `ans` last result, clear errors with position.
**Non-goals:** no floats >double precision, no CAS, no symbolic math.
**Tests (≥30):** precedence, associativity, each function (known values ±1e-9),
error cases (unbalanced paren, div-by-zero → "error: divide by zero", unknown
token with position), variable store, interactive REPL smoke.
**Acceptance:** `calc "2^10"` → `1024`; test driver exits 0 printing `ALL PASS`.

## §2 File utilities (`a-*`) — F1-2

**Tools:** `a-ls [-l] [path]`, `a-cat FILE...`, `a-cp SRC DST`, `a-mv SRC DST`,
`a-find PATH -name PATTERN [-type f|d]`, `a-rm [-r] PATH` (refuses `/`, `/ai`
without `--force-ai` and never touches `/usr` etc. by path-prefix check).
**Behavior:** clear usage errors exit 2; real errors exit 1 with message to stderr;
success exit 0. Implement in C or shell; tests via a fixture tree in
`tests/fixtures/`.
**Tests (≥20):** happy paths + usage errors + guard tests (a-rm refuses `/`,
refuses `/ai` without flag, refuses nonexistent).
**Acceptance:** `tests/run.sh` prints per-tool PASS lines, exits 0.

## §3 Text editor (`aed`) — F1-3

**Interface:** `aed FILE` — line-based TUI (raw terminal mode): movement, insert,
delete line, `/find`, `:w` save, `:q`/`:wq`, undo (single-level buffer ok).
**Tests (≥15):** headless buffer API tests (the UI layer is thin over a testable
core: `buffer.c` with load/save/edit/search), file round-trip, CRLF handling,
search no-match.
**Acceptance:** `tests/run.sh` green + human 2-minute smoke in a real terminal.

## §4 Job runner (`jobs`) — F1-4

**Interface:** `jobs start CMD...` → prints job id; `jobs list`; `jobs kill ID`;
`jobs log ID`.
**Mechanics:** fork + setsid, log to `/ai/state/jobs/<id>.log`, pidfile. Sandbox-
compatible (child of harness sandbox when agent-built via shell tool).
**Tests (≥10):** start/sleep/log content/list shows state/kill actually kills.
**Acceptance:** suite green; `jobs kill` verified by process absence.

## §5 Console assistant (`ask`) — F1-6

Thin CLI → harness `ask` path (no tools, chat params from doc 04 §3). Acceptance:
round-trip latency < model_time + 1 s; streams output.

## §6 Networking suite — F2-*

**a. Bring-up playbook (agent session, not code):** ordered steps with per-step
verification:
```
1 ip link                      # observe iface name
2 ip link set wlan0 up         # GATE (privileged)
3 write /etc/wpa_supplicant.conf  # GATE; harness writes via privileged hook, not model fs_write
4 wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf   # GATE
5 dhcpcd wlan0                 # GATE
6 verify: ip addr show wlan0 | grep inet       # expect non-loopback
7 verify: getent hosts huggingface.co          # DNS works
8 write /ai/state/net.json
```
Each step's expected evidence is in the playbook; agent reports per-step result.

**b. `libhttp` (C):** `http_get(url, opts)` → status, headers, body buffer.
TLS via vendored `mbedtls` (musl-friendly, small) or `libtls`. Features: HTTP/1.1,
chunked encoding, redirects (≤5, configurable), timeouts, max size cap, HTTPS.
**Tests (≥12):** against a local test server the agent also builds (Python
`http.server` fixtures are fine — host has Python or the agent writes a tiny C
test server), plus one live probe gated on network. Chunked, redirect, TLS,
timeout, 404, big-body cap.
**Acceptance:** `libhttp/tests/run.sh` green; `a-fetch https://example.com`
returns 200 body.

**c. `a-ping`:** ICMP via raw socket (CAP_NET_RAW — sandbox note: run under
gate-approved privileged wrapper) or TCP-connect fallback mode. Tests: loopback
ping.

## §7 Cloud bridge (`cloudbridge`) — F3-1..4

**Daemon** at `127.0.0.1:8081`, OpenAI-compatible `/v1/chat/completions`.
**Config** `/ai/state/router.json`:
```json
{"routes": [
  {"match": {"context_gt": 6000}, "provider": "cloud", "model": "claude-..."},
  {"default": true, "provider": "local", "model": "qwen2.5-coder-7b"}
],
 "cloud": {"endpoint": "https://api.anthropic.com/v1/...", "key_file": "/ai/secrets/provider.key", "timeout_s": 60},
 "fallback": "local", "offline_floor": true}
```
**Behavior:** read key from file (never from request), forward, translate response
shape, stream support optional v1. On cloud error/timeout → retry local silently
(log the fallback event). `offline_floor`: if network probe fails → local only,
fast (no 60 s hang — probe cached 30 s).
**Tests (≥12):** mock upstream server for: success translate, 401 → local
fallback, timeout → local, streaming passthrough (stretch), key redaction in logs,
offline floor.
**Acceptance:** suite green; harness pointed at 8081 completes a Phase-1-style
session.

## §8 Task engine (`tasks`) — F4-1

State `/ai/state/tasks.json`: `{id, title, depends[], status[pending|active|done|
failed], acceptance_cmd, notes}`. CLI: `tasks add/list/next/done`. The *harness*
reads it for state summaries (doc 05 §7.1) and session resume. Acceptance: kill a
session mid-task, new session resumes from tasks.json and continues correctly.

## §9 Text browser (`wbrowse`) — F4-2

**Interface:** `wbrowse URL` → rendered text page; keys: `j/k` scroll, `Enter` open
link under cursor, `b` back, `q` quit, `:open URL`.
**Pipeline:** libhttp fetch → HTML parser (minimal: tags → text blocks, `<a href>`,
`<pre>` passthrough, ignore scripts/styles) → line-wrapped render with numbered
links `[1]`.
**Tests (≥15):** fixture HTMLs (headings, lists, links, nested, entities
`&`, pre blocks), history stack, redirect handling.
**Acceptance:** renders a provided fixture and `example.com` live; link nav works
in a 2-min human smoke.

## §10 Package export/install (`aipkg`) — F4-3

`aipkg export NAME... → /ai/out/name-<ver>.aipkg` (tar: manifest, src, tests,
registry entry). `aipkg install FILE` → unpack, run tests, register. Acceptance:
export on machine 1 → install + `selftest` on machine 2 (AC-5).

## §11 Selftest (`selftest`) — F4-4

Runs every registered app's `tests/run.sh` in sandbox; prints table
(name/pass/secs); exit 0 iff all pass; writes `/ai/state/selftest-<ts>.json`.
Harness can gate future sessions on a green selftest.
