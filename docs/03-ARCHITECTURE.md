# 03 — Architecture

The system is a strict layer stack. Each layer is only allowed to depend on the
layers below it. The agent's code lives almost entirely in **Layer 4**; everything
below is the small, stable, human-written foundation.

```
┌─────────────────────────────────────────────────────────────────┐
│ L5  GROWTH      tasks engine, package/export, update loop       │  agent-built
├─────────────────────────────────────────────────────────────────┤
│ L4  /ai  APPS + LIBS + REGISTRY      (all agent-written code)   │  agent-built
│     /ai/bin  /ai/apps  /ai/lib  /ai/registry.json  /ai/state    │
├─────────────────────────────────────────────────────────────────┤
│ L3  CLOUD BRIDGE   cloudbridge daemon + model router            │  agent-built (L4 product)
├─────────────────────────────────────────────────────────────────┤
│ L3  AGENT HARNESS  loop · tools · sandbox · checkpoint · gates  │  human-written (~3k LOC)
├─────────────────────────────────────────────────────────────────┤
│ L2  MODEL RUNTIME  llama-server (OpenAI-compatible HTTP)        │  vendored
├─────────────────────────────────────────────────────────────────┤
│ L1  HOST OS        Linux + busybox/coreutils + gcc + wifi stack │  shipped config
├─────────────────────────────────────────────────────────────────┤
│ L0  HARDWARE       bare metal: x86-64 or Apple Silicon          │
└─────────────────────────────────────────────────────────────────┘
```

## 1. Directory contract (the "OS surface")

Everything the agent owns is under `/ai`:

```
/ai/
  bin/            executables the user invokes (registered apps)
  apps/           source of agent-built apps, one dir per app
    calc/         src/, tests/, manifest.json
    libhttp/      shared library + tests
    ...
  lib/            compiled shared libs
  registry.json   machine-readable app registry (schema v1)
  state/          agent's own notes: net.json, tasks.json, session logs
  secrets/        0600 API keys (Phase 3+)
  tmp/            scratch; wiped between sessions
  models/         GGUF files (F0-2)
```

Host-owned: `/usr`, `/etc` (only the harness may touch `/etc/wpa_supplicant.conf`,
and only via approval gate).

## 2. Layer contracts

### L1 Host
Ships: Linux kernel, busybox/coreutils, `gcc`/`clang`, `make`, toolchain, terminal,
`ip`, `iw`, `wpa_supplicant`, `dhcpcd`, `curl` (dev-side only), `openssh` (optional
remote admin). No GUI, no daemons beyond a getty and the model server.

### L2 Model runtime
`llama-server` bound to `127.0.0.1:8080` exposing `/v1/chat/completions` with:
tool-call parsing, seed pinning, context 8192, GPU offload when available. One
responsibility: text/tools in, text/tools out, fast. A **health endpoint** the
harness probes at boot.

### L3 Agent harness (the crown jewel — spec in doc 05)
A single long-running process (`aiosd`) plus a thin CLI (`aios`). Responsibilities:
1. Agent loop: prompt assembly → model call → parse tool call → execute → feed result
   → repeat, bounded.
2. Tools: `shell`, `fs_read`, `fs_write`, `proc`, `registry`, `checkpoint`,
   `ask_human`. (Minimal set; see doc 05 §4.)
3. Sandbox: every `shell` executes inside namespace isolation with fs roots `/ai`,
   `/tmp`, read-only `/usr`, `/etc`.
4. Checkpoint: pre-session snapshot of `/ai` (+approval-gated host files) to
   `/ai/checkpoints/<ts>/`.
5. Gates: privileged-command allowlist requiring human y/n (doc 09 §3).
6. Budgets: wall-clock, tokens, tool-call count, disk delta per session.
7. Registry: the only writer of `/ai/registry.json`.
8. Logs: append-only JSONL at `/ai/state/sessions/<id>.jsonl`.

### L3b Cloud bridge (agent-built, Phase 3)
Local HTTP daemon on `127.0.0.1:8081`, OpenAI-compatible. Routes per task class:
`code_small → local`, `long_context|frontier → cloud`, with local fallback. The
harness is unaware whether it's talking to local or cloud — the router decision is
configuration in `/ai/state/router.json` the agent itself maintains.

### L4 /ai applications
Everything built by agent sessions. Apps must:
- live in `/ai/apps/<name>/` with `src/`, `tests/`, `manifest.json`,
- be installed as `/ai/bin/<name>` (or registered lib),
- pass their test suite before the harness marks `tests_pass: true`,
- never write outside `/ai` (enforced by sandbox anyway).

### L5 Growth systems
Task engine (decomposition + resume), package export (registry+src+tests tarball),
self-test loop. All *implemented by the agent* in Phase 4 as more `/ai` apps; the
harness only provides persistence hooks (registry, state files).

## 3. Boot & run flow

```
power → GRUB → Linux boot → getty → login (user: ai)
      → /ai/bin/boot-ai (agent-written later; shell script early)
           → llama-server --port 8080 (waits for /health)
           → aiosd (harness daemon) → prints "harness ready>"
      → user at console:  aios            (interactive agent session)
                          ask "<prompt>"   (one-shot chat, harness-less)
                          /ai/bin/calc 2+2 (agent-built app)
```

## 4. Data flow of one agent session

```
user goal
   → harness: assemble system prompt + goal + state summary (doc 08)
   → model → tool_call(shell: "gcc calc.c -o /ai/bin/calc")
   → sandbox exec → output
   → model → tool_call(shell: "cd /ai/apps/calc/tests && ./run.sh")
   → test output → model → patch (fs_write) → retest
   → model → tool_call(registry: install calc)
   → harness: registry write + checkpoint note
   → session log → user verdict
```

Every arrow is budgeted and logged (N6).

## 5. Failure & recovery model

- Any model/tool failure mid-session → harness halts, offers `rollback` to the
  pre-session checkpoint (N4), or `resume` from the last successful task step.
- llama-server crash → harness restarts it, resumes the session (tool loop is
  stateless per step; state lives in the harness + `/ai/state`).
- Corrupt registry → rebuilt from `/ai/apps/*/manifest.json` (source of truth is the
  manifests, registry is derived).

## 6. Multi-machine path (Phase 4)

Machine #2 installs the same L1+L2 image, then restores a package tarball (F4-3) —
registry, sources, tests — and runs `selftest`. The "OS image" is therefore:
**host config + harness + model artifact (SHA-pinned) + knowledge package**. Nothing
else is needed for reproducibility.
