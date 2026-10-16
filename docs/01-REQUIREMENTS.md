# 01 — Requirements (Requirements Engineering)

Status: baseline v1.0 · Owner: AI OS project · Derived from doc 02 research findings.

---

## 1. Product vision (one sentence)

A computer that boots with an on-board LLM and a tiny agent harness, from which the
user and the AI jointly construct every subsequent piece of software the machine and
user need.

## 2. Stakeholders

| Stakeholder | Interest |
|---|---|
| **Builder** (you) | Ships the harness and bootstrap; wants a tractable, phase-gated build |
| **User** | Wants a working computer whose software they can grow on demand |
| **The agent** | The "user" of the OS API surface; needs stable tools, fast compile-test loops |
| **Downstream/second machines** | Later users installing from a Phase-4 image; need reproducibility |

## 3. User stories (top 15)

1. As a builder, I can boot a machine into AI OS with no network and see the harness
   ready, so that the system is verifiable offline.
2. As the agent, I can run shell commands, read/write files, and spawn/kill processes
   within a sandbox, so that I can build and test software.
3. As a user, I can ask "make me a calculator" and receive a working, registered
   application within one bounded agent session.
4. As a user, I can see a registry of everything the agent has built, with source
   location, version, and test status.
5. As the agent, when networking is requested, I can bring up Wi-Fi/Ethernet + DHCP +
   DNS using configuration tools and prove connectivity with an HTTP probe.
6. As the agent, once networked, I can call a frontier cloud model through a bridge I
   wrote, and fall back to my local model on failure.
7. As a builder, I can review any proposed privileged action (partition, useradd,
   network config) as a diff before it executes.
8. As a user, I can veto or roll back any change the agent made (checkpoint/restore).
9. As a builder, I can run the full eval suite offline and get a pass/fail report per
   capability.
10. As the agent, I can run a project's tests and read failures, so I can repair my
    own code in a bounded loop.
11. As a user, I can type `ask` at the console and converse with the system's model.
12. As a user, I can export the app registry and sources as a package for a second
    machine ("what this OS has learned").
13. As a builder, I can see token/cost budgets per agent session and hard caps.
14. As the agent, I can decompose a large app into tasks, checkpoints, and resume.
15. As a user, I can pin the system to an approved checkpoint and forbid further
    writes until I say so.

## 4. Functional requirements

Grouped by phase; IDs are stable and referenced by specs/tests.

### F0 — Platform (shipped code)

| ID | Requirement | Notes |
|---|---|---|
| F0-1 | Boot minimal Linux with <512 MB disk footprint and no unneeded daemons | Alpine/NixOS-min; see doc 02 |
| F0-2 | Load and run one quantized GGUF model at ≥10 tok/s single-stream | llama.cpp server or direct lib |
| F0-3 | Provide `/ai/bin` and `/ai/apps` directories; the registry at `/ai/registry.json` | |
| F0-4 | Harness exposes ≥3 tools to the model: `shell`, `fs_read/fs_write`, `proc` | schema in doc 05 |
| F0-5 | Harness enforces sandbox (namespace/isolation) on all agent shell calls | see doc 09 |
| F0-6 | Harness checkpoints the filesystem tree before every session that writes | rsync/overlay snapshot |
| F0-7 | Harness enforces per-session budgets: wall-clock, tokens, disk, process count | |
| F0-8 | Human approval gate: any command matching the privileged list requires interactive y/n | list in doc 09 |

### F1 — Self-constructed base software (agent-built)

| ID | Requirement |
|---|---|
| F1-1 | Calculator: expression eval, incl. precedence, functions (sin/cos/log/sqrt/pow), variables; interactive and one-shot modes; ≥30 passing tests |
| F1-2 | File utilities: `a-ls, a-cat, a-cp, a-mv, a-rm (guarded), a-find` — thin but safe wrappers with usage errors; ≥20 tests |
| F1-3 | Text editor: terminal UI, open/save, search; ≥15 tests |
| F1-4 | Job runner: run commands in background, list, kill; ≥10 tests |
| F1-5 | Every F1 app registers in `/ai/registry.json` with schema v1 (name, path, entry, version, tests_pass, built_at, model, checksum) |
| F1-6 | `ask` console REPL for conversation with the model |

### F2 — Networking (agent-configured + agent-built)

| ID | Requirement |
|---|---|
| F2-1 | Agent brings up one interface (Ethernet DHCP or Wi-Fi WPA) using existing OS tooling (`ip`, `wpa_supplicant`, `dhcpcd`) it drives via its shell tool |
| F2-2 | DNS resolution configured and verified (probe resolves `huggingface.co`) |
| F2-3 | HTTP(S) client library in `/ai/apps/libhttp` with ≥12 tests (GET, redirects, TLS, timeouts, chunked) |
| F2-4 | `ping`, `wget`-equivalent utilities registered |
| F2-5 | Network state file `/ai/state/net.json` the agent updates |

### F3 — Cloud escalation (agent-built)

| ID | Requirement |
|---|---|
| F3-1 | Bridge daemon `cloudbridge` implementing OpenAI-compatible chat API locally, proxying to a configurable remote provider; ≥12 tests |
| F3-2 | Model router: task-class → model mapping (code→local or cloud, long-context→cloud); local fallback on any cloud failure/timeout |
| F3-3 | API key stored at 0600 in `/ai/secrets/`; never logged, never in registry |
| F3-4 | Offline mode: bridge fails fast and harness routes local with no user-visible stall >2 s |

### F4 — Growth (agent-built, cloud-augmented)

| ID | Requirement |
|---|---|
| F4-1 | Task engine: agent decomposes large requests into tasks with dependencies, persists to `/ai/state/tasks.json`, resumes across sessions |
| F4-2 | Text browser: HTTP/1.1, HTML→text rendering, links, history; ≥15 tests |
| F4-3 | Package/export: registry + sources + tests → tarball installable on machine #2 |
| F4-4 | Update loop: agent re-runs its own test suite on demand (`/ai/bin selftest`) |

## 5. Non-functional requirements

| ID | NFR | Target |
|---|---|---|
| N1 | **Offline-first** | Phases 0–2 complete with network interface down |
| N2 | **Latency** | Tool round-trip (model think + tool exec) ≤5 s p50 on 7B@local |
| N3 | **Determinism** | Eval suite reproducible: same model+seed ⇒ same verdict per test ≥90% |
| N4 | **Recoverability** | Any agent session fully revertible to pre-session state in <30 s |
| N5 | **Footprint** | Shipped code (harness + host config) ≤6,000 LOC, human-written |
| N6 | **Observability** | Every session logged (prompt hash, tool calls, diffs, verdicts) JSONL |
| N7 | **Safety** | Zero writes outside sandbox roots; privileged list enforced; secrets never emitted |
| N8 | **Portability** | Host layer runs on x86-64 Linux and Apple Silicon (macOS host for dev) |
| N9 | **Token economy** | Phase 1 fully buildable within 10M local tokens (i.e., no API cost) |

## 6. Constraints

- C1: Human-written code limited to host provisioning + harness + eval framework.
- C2: Model must fit on-device; no offload at Phase 0.
- C3: No modifications to the Linux kernel.
- C4: All agent-written code lives under `/ai/` — never replaces host binaries.
- C5: Phases are strictly sequential; a phase's exit criteria gate the next (doc 06).

## 7. Acceptance criteria (system level)

**AC-1 (Phase 0):** Cold boot to `harness ready> ` prompt on target hardware, network
physically disconnected. Measured: boot log + `net.interface == down`.

**AC-2 (Phase 1):** From clean checkpoint, agent session builds calculator + 2 file
utilities, all tests green, registry consistent, within budget (≤60 min, ≤2M tokens).
Reproduced on 3 independent runs.

**AC-3 (Phase 2):** Clean checkpoint → agent enables Wi-Fi with supplied credentials,
HTTP probe succeeds, `libhttp` tests pass — zero human commands beyond credential
entry and gate approvals.

**AC-4 (Phase 3):** With network up, agent writes `cloudbridge`, tests green, a routed
query answers via cloud model, and yanking the network mid-session causes clean local
fallback (session survives).

**AC-5 (Phase 4):** Text browser renders a provided static HTML page with links
navigable; registry export installs on second machine and `selftest` passes there.

## 8. Out of scope (v1)

GUI desktop environments; multi-user; kernel development; training/fine-tuning;
self-modification of the harness itself (explicitly gated OFF until Phase 5 review);
arbitrary internet ingestion without allowlists.
