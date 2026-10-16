# 12 — Glossary & References

## Glossary

| Term | Meaning |
|---|---|
| **Harness** | The human-written agent runtime (`aiosd`/`aios`): loop, tools, sandbox, gates, checkpoints |
| **Session** | One bounded agent run with a goal, budget, event log, and verdict |
| **Gate** | Human approval required before a privileged command executes |
| **Checkpoint** | Filesystem snapshot of `/ai` enabling rollback |
| **Registry** | `/ai/registry.json`, derived from per-app manifests; the OS's app database |
| **Playbook** | A step-verified procedure the agent executes via tools (e.g., net bring-up) |
| **Verdict** | Harness-computed session outcome; never the model's own claim |
| **Offline floor** | Invariant: the system remains fully functional without network |
| **Escalation ladder** | The phase sequence by which the system gains capability, itself |
| **T1/T2** | Hardware tiers (doc 04 §1) |
| **aipkg** | The agent-built package format (registry + sources + tests) |
| **State summary** | ≤300-token context injected each turn (doc 05 §7) |

## References & prior art

**Local inference**
- llama.cpp + `llama-server` (OpenAI-compatible API) — github.com/ggerganov/llama.cpp
- MLX / MLX-LM (Apple Silicon) — github.com/ml-explore/mlx
- GGUF quantization formats, Q4_K_M quality notes — llama.cpp docs

**Models** (verify current versions at build)
- Qwen2.5-Coder (3B/7B/14B-Instruct, GGUF) — tool-calling trained
- Llama 3.1 8B Instruct — tool-calling trained
- DeepSeek-Coder-V2-Lite (MoE), Gemma 2 9B — alternates

**Agentic coding prior art**
- SWE-agent (Princeton), OpenHands, Aider — edit-test-repair loop literature
- SWE-bench / SWE-bench Verified — verify-then-accept benchmark methodology
- Anthropic "Building effective agents" (2024–25) — small-tool, bounded-loop design
  patterns this spec consciously follows

**Minimal Linux**
- Alpine Linux (musl, ~130 MB base), busybox, runit-style init
- Buildroot / NixOS — Phase 5/6 image-research paths

**Security primitives**
- Linux namespaces (mount/pid/net), seccomp-BPF, `no_new_privs` — sandbox basis
- Landlock (LSM) — alternative/additional MAC layer worth adding in Phase 3

**Userland building blocks the agent will lean on**
- wpa_supplicant, dhcpcd/iwd, `ip(8)` (iproute2) — Phase 2
- mbedtls or libtls — TLS for libhttp
- musl + gcc/clang — toolchain

## Document set internal cross-references

- Requirements → docs/01 · Feasibility → docs/02 · Architecture → docs/03
- Model/hardware → docs/04 · Harness contract → docs/05 · Build order → docs/06
- Per-app specs → docs/07 · Prompts → docs/08 · Security → docs/09
- Evals → docs/10 · Risks → docs/11

## Maintenance

Model-dependent facts (versions, sizes, scores) carry a "verify at build" tag.
Update doc 02 quarterly; risk register at every gate; requirements IDs never
mutate — supersede instead.
