# 06 — Bootstrap Roadmap

Phase-gated. Each phase has: goal, entry condition, work, exit criteria (gates),
rollback. Phases are strictly sequential (C5). Time estimates assume one builder
part-time plus the agent.

---

## Phase 0 — Host provisioning (human-built) · ~1–2 weekends

> **Emulator-first (2026 update):** Phase 0 is now split.
> **Phase 0a — Emulator (default path):** build the VM environment per doc 13
> (`emulation/vm.sh fetch/create/boot/wait` + `model-host.sh`), snapshot `clean`,
> and pass gates G0a-1..3 below. All Phase 1–4 work happens in this VM, driven by
> mainstream coding agents via `AGENTS.md`.
> **Phase 0b — Bare metal (deferred until Phase 4 evals pass):** repeat the steps
> below on real hardware; only G0-3 (Wi-Fi reality check) and final packaging
> require it.

**Goal:** bare metal boots into a minimal Linux where the model runs and the harness
prompts `ready>`. *(In Phase 0a the "machine" is the emulator VM; the same steps
apply.)*

Work:
1. Install Alpine Linux (ext4, `/ai` partition, no GUI). Or NixOS-min if preferred;
   keep musl + gcc.
2. Packages: `busybox coreutils gcc make musl-dev linux-firmware iw
   wpa_supplicant dhcpcd git curl openssh` (+ `clang` optional).
3. Build/vend llama.cpp; install `llama-server`.
4. Download pinned model GGUF (doc 04 §2) → `/ai/models/`, record SHA-256.
5. Write harness (per doc 05) — this is the bulk of human code (~3k LOC).
6. Smoke test: `ask "what is 2+2"` works offline.

**Exit gates:**
- G0a-1 *(emulator)*: `emulation/vm.sh` doctor/create/boot/wait/exec all pass on
  the M3 Mac; VM has `/ai` skeleton, `ai` user, model endpoint reachable (AE-1..7).
- G0-1: cold boot → `harness ready>` <90 s after login.
- G0-2: eval harness runs; baseline model scores recorded (doc 10 §2).
- G0-3: **human pre-verified Wi-Fi once manually** on real target hardware
  (driver/firmware reality check — cannot be done in the emulator; do not skip).
- G0-4: sandbox blocks: read of `/etc/shadow`, write to `/usr`, network from a
  Phase-0 session.

**Rollback:** emulator: `vm.sh rollback clean`. Hardware: n/a (foundation). Keep the install USB.

---

## Phase 1 — Self-constructed base software (agent-built) · ~1–2 weeks elapsed

**Goal:** from a clean checkpoint, agent sessions build the F1 apps with tests.

Work (each = one agent session, human supervises):
1. Task: calculator (F1-1) — session brief from doc 08 P1-CALC.
2. Task: file utilities `a-ls a-cat a-cp a-find` (F1-2).
3. Task: `ask` console REPL (F1-6).
4. Task: text editor (F1-3).
5. Task: job runner (F1-4).
6. Registry + manifest discipline matures here (F1-5).

Builder's role: run sessions, approve nothing beyond defaults (no privileged ops in
this phase), inspect diffs, tag good checkpoints. Fix harness bugs — that's Phase 1's
real purpose: **shakedown of the loop**.

**Exit gates:**
- G1-1: ≥5 apps registered, all `tests_pass: true`, from ≥3 independent session runs
  per app (N3: reproducibility).
- G1-2: full suite ≤2M tokens, ≤60 min wall on T2 hardware (AC-2).
- G1-3: `selftest`-style aggregate runner exists (agent-built or harness flag) and
  passes.
- G1-4: audit: zero files written outside `/ai` (log scan).

**Rollback:** checkpoint per session; discard app dirs that failed.

---

## Phase 2 — Networking (agent-driven) · ~1 week

**Goal:** the agent brings the machine online and writes the first networked code.

Work:
1. Interactive session (human at console): "Bring up Wi-Fi. Credentials follow."
   Agent drives `ip`/`wpa_supplicant`/`dhcpcd` via `shell` — each privileged command
   passes gate G, human presses `y`.
2. Agent writes `/ai/state/net.json` from observed state.
3. Agent session: build `libhttp` (F2-3) + `a-ping`, `a-fetch` (F2-4) — now it can
   test against real endpoints.
4. Agent session: DNS config + verification probes.

**Exit gates:**
- G2-1: probe `https://huggingface.co` 200-OK from `libhttp` test.
- G2-2: net.json matches `ip addr` truth.
- G2-3: unplug cable → agent detects (via its own probe script) and reports.
- G2-4: secrets discipline: credentials only in wpa conf / env, never in logs
  (redaction verified, N7).

**Rollback:** checkpoint pre-session; `checkpoint.rollback` returns to offline state.

---

## Phase 3 — Cloud escalation (agent-built bridge) · ~1 week

**Goal:** the agent gives itself frontier capability through a bridge it wrote, with
local fallback.

Work:
1. Human: obtain API key for chosen provider (Anthropic/OpenAI/Gemini/OpenRouter).
   Deliver via `ask_human` secret-entry (harness writes `/ai/secrets/`, 0600, model
   never sees the raw value in history — gate + redaction).
2. Agent session: build `cloudbridge` (F3-1, spec doc 07 §6) + tests.
3. Agent session: build router config (F3-2), wire harness model endpoint to
   `127.0.0.1:8081`.
4. Failure-injection test: kill network mid-session → harness continues on local.

**Exit gates:**
- G3-1: routed query answered via cloud; log shows route decision.
- G3-2: network kill → session survives, local fallback <2 s (F3-4).
- G3-3: key never appears in any session log (automated grep of JSONLs).
- G3-4: offline re-test: boot with network down → everything Phase 0–1 still works.

**Rollback:** router.json reverts to `local_only` (harness flag `--offline`).

---

## Phase 4 — Growth (cloud-augmented) · ongoing

**Goal:** bigger software, built by the now-frontier-capable agent under the same
gates.

Sequence (each its own spec/acceptance in doc 07):
1. Task engine (F4-1) — decomposition, resume.
2. Text browser (F4-2).
3. Package export/install (F4-3) → **machine #2 test** (AC-5).
4. Update loop / selftest formalized (F4-4).
5. Stretch: TUI shell replacement, markdown viewer, JSON tool, cron-like scheduler,
   simple GUI (Wayland + small toolkit) — one at a time, test-gated.

**Exit gates per item:** its subsystem spec's acceptance criteria (doc 07) + audit.

---

## Phase 5 — Stabilization & research frontier

- Long-horizon autonomy (multi-day tasks with checkpoints), harness self-modification
  review board (still human-gated), custom initramfs image (Buildroot) research,
  capability distillation (fine-tune a local model on the machine's own successful
  sessions — a genuinely interesting research thread: the OS teaches itself).

## Timeline summary

| Phase | Duration | Token cost | Cloud cost |
|---|---|---|---|
| 0 | 1–2 wk | — | — |
| 1 | 1–2 wk | ≤2M local | $0 |
| 2 | 1 wk | ≤1M local | $0 |
| 3 | 1 wk | ≤1M local | ~$5–20 evals |
| 4 | ongoing | mixed | usage-based |

## Operating discipline (all phases)

1. One goal per session. 2. Checkpoint before, review diff after. 3. Never approve
privileged ops you haven't read. 4. Tag checkpoints at every exit gate. 5. Log
everything; assume logs are the only truth about what the agent did.
