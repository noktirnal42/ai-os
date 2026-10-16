# 05 — Agent Harness Specification

The harness is the only substantial human-written code (F-N5: ≤3k LOC). This spec is
written at implementation precision. Reference language: C (target) with a
Rust/Python reference implementation acceptable on the dev host; the contract, not
the language, is normative.

---

## 1. Process model

```
aiosd     — daemon: owns the model connection, session state, registry writer
aios      — CLI:   starts/attaches sessions, renders events to the terminal
ask       — CLI:   one-shot chat (no tools), cheapest path
```

`aiosd` hosts one session at a time (v1). Session = {id, goal, budget, event log,
sandbox instance, checkpoint}.

## 2. Agent loop (normative pseudocode)

```
session = start(goal, budget)
emit(SystemPrompt, assemble(system_role, goal, state_summary(), tool_schemas()))
loop:
  resp = model.call(history, tools)            # temperature/params per doc 04 §3
  if resp.has_tool_call:
      if gate.required(call) and not ask_human(call): 
          history += denial(call); continue
      result = sandbox.exec(call, timeout=tool_timeout(call))
      history += tool_result(result)            # truncated to 4k chars (doc §7)
      tool_calls += 1
  elif resp.has_text:
      emit(AgentMessage, resp.text)
      if resp.text.marked_final: break
  if tool_calls > budget.max_tools: break "budget"
  if wall_clock() > budget.max_seconds: break "budget"
finalize: verdict, registry diff, session log, offer rollback|resume
```

Loop invariants:
- **Bounded**: every loop has a hard tool-call and wall-clock budget (default: 200
  tool calls, 45 min; per-phase overrides).
- **Stateless steps**: each model call is complete; no hidden state beyond `history`.
- **Verifiable**: the loop never declares success on its own say-so; success claims
  must reference a passing command (`tests_pass`, exit code) — see §6.

## 3. Tool catalog

Exactly seven tools. Resist adding more; every tool is prompt surface and attack
surface.

| Tool | Schema (abridged) | Behavior |
|---|---|---|
| `shell` | `{cmd: string, timeout_s?: int≤300, workdir?: path∈/ai\|/tmp}` | Exec in sandbox (§5). Returns `{exit, stdout, stderr, truncated}` |
| `fs_read` | `{path, offset?: int, max_bytes?: int≤65536}` | Read-only file access, sandbox-checked |
| `fs_write` | `{path, content, mode?: "overwrite"\|"append"}` | Only under `/ai`; refuses host paths |
| `proc` | `{op: "list"\|"kill", pid?}` | List agent-spawned procs; kill by pid (guarded) |
| `registry` | `{op: "install"\|"remove"\|"query", name, manifest?}` | Harness-only writer of registry.json |
| `checkpoint` | `{op: "create"\|"rollback"\|"list", tag?}` | Filesystem snapshot ops (§6) |
| `ask_human` | `{question, options?: [..], privileged_cmd?: string}` | Blocks for interactive y/n |

Notes:
- Model never calls `registry`/`checkpoint`/`ask_human` more than needed — prompt
  discourages; harness enforces rate (≤5 registry ops/session).
- `shell` stdout/stderr **truncated at 4,096 chars each** with a head+tail merge so
  the model sees the beginning (compile errors) and end (summary) — critical for
  small-context quality (doc 02 R6).

## 4. Tool-call format & fallback

Preferred: model-native tool calling (Qwen2.5/Llama-3.1 format via llama-server's
`tools` parameter). Fallback (no-native-format models): **JSON-strict protocol** —
system prompt mandates the model end each turn with exactly one fenced JSON block:

```json
{"tool": "shell", "args": {"cmd": "gcc -o /ai/bin/calc /ai/apps/calc/src/calc.c"}}
```
A parse failure injects one corrective message, max 2 per session before the harness
downgrades to plain chat + human relaying.

## 5. Sandbox (see doc 09 for threat model)

Linux implementation: `unshare(CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWNET?)` +
`mount --bind` with:
- `/ai` → rw
- `/tmp` → rw (tmpfs, per-session)
- `/usr`, `/lib`, `/etc` → **read-only bind**
- `/home`, `/root`, `/mnt`, `/media`, `/dev/sd*` → **not present**
- `no_new_privs` + seccomp allowlist (exec, file, net for Phase 2 sessions, fork)

macOS dev host: `sandbox-exec` profile equivalent (RW `/ai`, RO system), best-effort
(documented divergence).

Network: Phase 0–1 sessions run with network **disabled** in the sandbox (nothing to
talk to anyway); Phase 2+ sessions enable network only after gate approval for the
session.

## 6. Checkpoints

`checkpoint.create` = rsync `/ai` → `/ai/checkpoints/<ISO-ts>-<tag>/` (excludes
`checkpoints/`, `tmp/`, `models/`). Retention: keep last 20 + all tagged.
`checkpoint.rollback <id>` = reverse-rsync + registry rebuild from manifests
(F-rmp: manifests are source of truth). Checkpoint before: every session start
(harness-automatic) + any `registry install` (optional, tagged).

Rollback is the human's undo (user story 8) and the agent's own safety net during
multi-task builds.

## 7. Context management (the small-model problem)

Long contexts destroy 7B quality and latency. Rules:
1. **State summary injection**: each turn, harness prepends a ≤300-token summary:
   goal, task list state, last 3 tool results (hash-referenced), registry state,
   budget remaining. Older history is summarized, not replayed.
2. **File access discipline**: prompt tells the model to read files in slices
   (`fs_read` offsets), never whole files >64k.
3. **Tool-result trimming** (§3) with `…[N chars elided]…` markers.
4. **Prompt caching**: llama-server prompt cache keeps the long system prompt
   resident across steps (same prefix → near-instant reuse).
5. **History compaction**: when `history tokens > 6.5k`, harness summarizes the
   oldest 60% via the model itself (`summarize` sub-call, cheap, temp 0).

## 8. Budgets & accounting

Session budget JSON (harness-owned, model sees a read-only view):
```json
{"max_tools": 200, "max_seconds": 2700, "max_tokens": 400000,
 "max_disk_mb": 512, "max_cloud_calls": 0}
```
On breach: loop stops, emits `budget_exhausted` event, session is `paused` not
`failed` — resumable (F4-1).

## 9. Verdict & success criteria

A session ends with one of: `succeeded` (all declared tasks verified), `partial`
(some verified; list), `failed` (error + rollback offered), `paused` (budget).
**Verified** means: the specific acceptance command named in the task (e.g. `cd
/ai/apps/calc/tests && ./run.sh && echo PASS`) exited 0 with the expected marker in
the sandbox. The harness computes verdicts; the model may only *claim* them.

## 10. Logging & observability (N6)

Append-only JSONL `/ai/state/sessions/<id>.jsonl`:
```json
{"t":"...","ev":"tool_call","tool":"shell","args":{...},"hash":"..."}
{"t":"...","ev":"tool_result","exit":0,"bytes":812}
{"t":"...","ev":"gate","cmd":"ip link set wlan0 up","human":"y"}
{"t":"...","ev":"verdict","kind":"succeeded","tasks":[...]}
```
Secrets (strings matching `/ai/secrets/*` file contents) are redacted at emit time.
Every prompt hash + model id + seed recorded → full reproducibility.

## 11. Non-goals for the harness

No planning engine (the model plans; harness only tracks a task list it writes to
`/ai/state/tasks.json` via `fs_write`), no retries-with-judgment (model drives
retries), no hidden tool synthesis, no self-modification (harness source is
read-only to the model; Phase 5 gate).
