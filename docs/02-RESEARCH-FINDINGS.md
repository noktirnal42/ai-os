# 02 — Research Findings

Findings that justify the design choices, with alternatives explicitly considered and
rejected. Compiled from the state of the art as of early 2026; re-verify versions
before build (model landscape moves quarterly).

---

## R1. Can a small local model actually do this? (capability)

**Finding: YES for Phase 1, conditionally for Phase 2–3, no for Phase 4 without cloud.**

Evidence basis:
- **Code-capable 7B-class models** (Qwen2.5-Coder-7B-Instruct, Llama-3.1-8B,
  DeepSeek-Coder-V2-Lite, Gemma-2-9B) score 60–90% on HumanEval-class tasks — writing
  small, self-contained programs (a calculator, a file wrapper, an HTTP client) is
  squarely in-distribution for them.
- **Tool-calling at 7B is reliable.** Qwen2.5 and Llama 3.1 families were trained with
  structured tool call formats; single-tool and few-tool loops execute correctly at
  85–95% call-format accuracy. Multi-tool, long-horizon agentic tasks remain the weak
  point — which drives the bounded-loop + verification architecture (doc 05) rather
  than hoping for long-horizon brilliance.
- **Self-repair loops work.** Compile → run tests → read failure → patch converges in
  ≤3 iterations for small programs in practice; this is the operating regime of every
  agentic coding benchmark.

**Implication:** Phase 1 is calibrated so each unit of work is (a) small, (b)
verifiable by a test the model can also read, (c) reparable in-loop. The model doesn't
need to be great; the *loop* needs to be airtight.

## R2. Runtime choice

| Option | Verdict | Why |
|---|---|---|
| **llama.cpp (GGUF)** | **Chosen (Linux target)** | Single binary, Metal/CUDA/Vulkan, OpenAI-compatible `llama-server`, quantized 7–14B at 10–60 tok/s, no Python dependency at runtime |
| MLX / MLX-LM | Chosen for **macOS dev host** | Best Apple-Silicon perf (M-series unified memory), but Linux support immature |
| Ollama | Rejected as core | Convenience wrapper; adds daemon + model management we don't control; fine as dev-side alternative |
| vLLM | Rejected | Built for batch serving; heavy (CUDA-first, GBs of deps), wrong regime for single-user interactive |
| ONNX Runtime / direct weights | Rejected | More integration work for no capability gain |

**Decision:** `llama-server` (from llama.cpp) as the model backend on target; MLX-LM
on the macOS development machine; identical HTTP API (OpenAI-compatible) in front of
both so the harness doesn't care.

## R3. Host OS choice ("bare metal")

| Option | Verdict | Notes |
|---|---|---|
| **Alpine Linux (musl)** | **Chosen for dedicated target** | ~130 MB base, no systemd, simple runit-style init, huge package availability when needed later; musl static linking helps agent-built C tools |
| NixOS minimal | Strong alternative | Perfect reproducibility but steep learning curve for agent; declarative config is agent-hostile in early phases (changing it requires understanding the DSL) |
| Debian netinst | Fallback | More familiar, bigger footprint (~1.5 GB) |
| Ubuntu Core / Fedora IoT | Rejected | Snaps/OSTree transactionality gets in the way of the agent freely building |
| Custom initramfs / Buildroot | Phase-6 research item | Ultimate minimalism, but blocks nothing now; revisit once the agent is capable of maintaining its own image |
| macOS host | **Chosen for dev machine** | Your workstation already runs MLX/llama.cpp; harness is portable; dev-loop faster than flashing boxes |

**Dev-loop update (emulator-first):** development and testing now happen in a
QEMU/HVF Alpine aarch64 VM *on the macOS host*, not on the host itself — the host
serves the model (Metal), the VM runs the AI OS stack. Full spec: doc 13. This
preserves the Alpine-target choice above (the VM runs that exact guest) while
giving snapshots, agent-driven automation, and safety before hardware.

**Key architectural point:** the OS itself is *not* rewritten. Linux kernel + core
userland (busybox/coreutils, toolchain, Wi-Fi stack) is shipped; the *agent-owned
layer* is `/ai/` — applications, libs, registry, state. The agent configures existing
system facilities (kernel networking via `ip`/`iw`/`wpa_supplicant`) rather than
reimplementing them. Reimplementing a TCP/IP stack is a research fascination, not a
prerequisite.

## R4. Model selection detail (see doc 04 for full matrix)

- **Phase-0/1 primary: Qwen2.5-Coder-7B-Instruct, Q4_K_M GGUF (~4.7 GB).** Best
  small-model code quality + native tool-calling format; 7B keeps latency low for
  interactive loop (user experience = agent responsiveness).
- **Better-hardware upgrade: Qwen2.5-Coder-14B or Llama-3.1-8B→13B-class, Q4/Q5.**
- **Tool-calling format:** prefer models with native tool-call training; harness also
  implements a JSON-strict prompt fallback (doc 05 §4) for models without it.
- **Embedding (for later retrieval):** small local embedder (e.g. 100–400M param GGUF
  embed model) for codebase search once `/ai` grows — Phase 4 item, not bootstrap.

## R5. Prior art scan

| System | What it proves | What it doesn't do (our delta) |
|---|---|---|
| **SWE-agent / OpenHands / Aider** | Agentic edit-test loops work on real codebases | They are developer tools *on* an OS, not the OS process model |
| **SWE-bench(-Verified)** | Verify-then-accept loops raise small-model success rates dramatically | Not oriented to building whole apps from scratch |
| **Gemini/Copilot CLI agents (2025–26)** | CLI tool agents are mainstream; cloud-dependent | Cloud-dependent; we invert: cloud is an escalation, offline is baseline |
| **Tiny Core / minimal distros** | Sub-100 MB systems run real workflows | No agent; software is pre-baked |
| **Bespoke "LLM OS" prototypes (academic)** | Validate the concept space | None achieve self-bootstrapping offline; most assume cloud or ship apps prewritten |
| **GPT-4-class "self-writing computer" demos** | Fun, viral | Demo-ware: no eval harness, no security, no recovery |

**Delta:** nobody has shipped the *reliability engineering* — sandbox, checkpoints,
approval gates, eval-gated escalation — around an offline small model doing the
construction. That is the project.

## R6. Performance envelope (measured class, not aspiration)

On M-series Mac (M1/M2/M3, 32 GB) via MLX or llama.cpp Metal:
- 7B Q4: ~25–60 tok/s single stream → a "think + tool call" step in 2–6 s.
- On RTX 4090 / 3090 (Linux): 7B Q4 ~80–140 tok/s; 14B ~40–70.
- On CPU-only Ryzen (16 GB): 7B Q4 ~5–12 tok/s — **viable but sluggish**; budget
  sessions accordingly, prefer 3B-class (Qwen2.5-Coder-3B) with more loop iterations.

Implication for harness design: **cache and batch aggressively** (doc 05 §7): prefix
caching of the long system prompt, keep context tight (<8k), avoid re-reading large
files, prefer small focused tasks. Agent UX at 10 tok/s dies with 30k-token contexts.

## R7. Networking bring-up reality check

Phase 2 does **not** require the model to know 802.11 handshake details; it requires
it to correctly sequence existing tools: `ip link set wlan0 up` → write
`wpa_supplicant.conf` → run `wpa_supplicant -B` → `dhcpcd wlan0` → verify DNS. This is
a ~10-step tool-call plan, each step verifiable (exit codes, `ip addr` output).
Small models handle such linear, verifiable sequences with the harness providing
*checklists* and state files. Risk: real-world driver quirks (firmware load timing).
Mitigation: the human pre-verifies Wi-Fi once on target hardware (Phase 0 gate, G0-3).

## R8. What "RE" needs to flag early (requirements risks)

1. **Browser expectations management.** A text/HTTP browser is Phase 4 achievable; a
   JS-capable graphical browser is a multi-month effort even with frontier models.
   Requirement F4-2 is deliberately scoped to text.
2. **GUI.** Deferred to Phase 5+ (Wayland + a minimal toolkit the agent uses);
   TUI-first keeps bootstrap tractable.
3. **Security surface of agent-built code.** Agent writes code that runs as the user;
   doc 09's sandbox + review gates are non-negotiable from Phase 1, not bolted on.
4. **Model supply.** GGUF artifacts are downloaded once and stored locally; pin
   SHA-256 of model files (F0-2 companion) so a second machine rebuilds identically.
