# 00 — Executive Summary

## What we are building

**AI OS** is a self-constructing operating system. At boot it ships with almost nothing:
a minimal Linux host, a quantized on-board LLM (7–14B parameters), and an **agent
harness** of roughly three thousand lines of code that gives the model a shell, a
filesystem, and a process manager. Everything else on the machine — the calculator,
text editor, networking stack configuration, HTTP client, browser, package registry,
and eventually a GUI — is **written by the model itself**, compiled, tested, and
registered as an application the user can run.

The machine starts deliberately primitive. It earns its capability.

## Why this matters

Three forces converge to make this feasible *now* (2025–2026):

1. **On-board model quality crossed the threshold.** A Q4-quantized 7B coder model
   (Qwen2.5-Coder-7B, Llama-3.1-8B, DeepSeek-Coder-V2-Lite) runs at 15–60 tok/s on
   consumer hardware (Apple Silicon M-series, RTX 4090, Ryzen AI 395) and is reliably
   capable of writing small, correct, self-contained programs — exactly the class of
   software the bootstrap phases demand.
2. **Tool-calling small models became standard.** Structured function calls, once a
   frontier-only capability, now work at 7B. This is what turns a language model into
   an *agent* rather than a chat window.
3. **AI-written software is a real pattern.** SWE-bench-class agents routinely write,
   compile, run, and repair code in a loop. We industrialize that loop as the *process
   model of the OS itself*, not a developer tool beside it.

## The escalation ladder (the core idea)

The system's entire trajectory is a capability ladder it climbs itself:

| Rung | Capability | How it's obtained |
|------|-----------|-------------------|
| 0 | Host boots, model runs | Shipped (the only code we write) |
| 1 | Agent writes shell utilities, calculator, editor | Local model + harness loop |
| 2 | **Network** (Wi-Fi/DHCP/DNS/HTTP) | Local model writes config + wrapper scripts around the existing kernel stack |
| 3 | **Cloud models** — the agent gives itself frontier capability | Local model writes an API client for its own future use; local model remains offline fallback |
| 4 | Bigger apps: browser, package manager, IPC, service manager | Cloud-augmented agent loop, human approval gates |
| 5 | Self-maintaining: the OS reads its own registry, tests, and repairs itself | Same loop, persistent |

Each rung is a strict precondition for the next, each has explicit exit criteria, and
each is reversible (checkpointed, human-reviewed).

## What we deliberately do NOT build

- No cloud dependency at boot. **The OS must reach Phase 2 with zero network.**
- No general-purpose desktop environment in the bootstrap. Phase 4+ addresses GUI.
- No arbitrary autonomous execution without approval gates. Phases 1–3 run inside a
  sandbox with an allowlist; destructive or privileged actions require human sign-off
  until the eval harness demonstrates a sustained safety record (see doc 09).
- No bespoke kernel work. The Linux kernel is a given; we write *userspace*, and the
  model configures the *existing* kernel networking stack rather than reimplementing it.

## Feasibility verdict

**GO** — with two hard constraints:

1. **Hardware floor.** 32 GB unified/system RAM, ≥16 GB free after host (runs 14B Q4).
   8 GB machines cap out at 3B models and will struggle at Phase 1 (doc 04).
   *Development happens on the builder's MacBook Pro M3 (18 GB) inside an emulator,
   with the model served on the host via Metal — see the build-strategy note below
   and doc 13.*
2. **Scope discipline.** Phase 1 targets ≤10 small apps with tests. "Browser" is a
   Phase 4 goal and starts as a ~500-line HTTP/1.1 text browser, not a Chromium clone.

**Build strategy — emulator-first.** All development and evaluation happens inside a
QEMU/HVF Alpine aarch64 VM on the M3 MacBook (18 GB), where the model runs on the
macOS host (Metal-accelerated) and the VM harness reaches it at `10.0.2.2:8080`.
Mainstream coding agents construct the system inside the VM through a single
scripted interface (`emulation/vm.sh`, doc 13). Hardware bring-up is the *last*
milestone, after the system has passed its phase gates in the emulator.

The dominant risk is not model capability but **agent reliability engineering** —
bounded loops, verification, and rollback — which is precisely what docs 05, 09, and
10 specify. The bootstrap model need not be brilliant; it needs to be *correct often
enough within a bounded self-repair loop*, and verification is cheap for the small,
well-specified programs Phase 1 demands.

## Deliverables of this documentation set

- A complete requirements baseline (doc 01) and architecture (doc 03).
- Research findings justifying every major choice, with alternatives rejected
  explicitly (doc 02).
- A buildable, phase-gated roadmap with exit criteria and rollback (doc 06).
- The agent harness specification at implementation precision (doc 05).
- The actual production system prompts (doc 08).
- Security, testing, and risk controls sufficient to run the system on real hardware
  with a human in the loop (docs 09–11).
