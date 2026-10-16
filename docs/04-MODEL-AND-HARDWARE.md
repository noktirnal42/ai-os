# 04 — Model & Hardware Selection

## 1. Hardware tiers

| Tier | RAM | Example | Model that fits | Verdict |
|---|---|---|---|---|
| **T1.5 — builder's machine (dev)** | 18 GB unified | **MacBook Pro M3 18 GB (this project)** | **7B Q4 on the host** (Metal, ~6 GB) served to the VM — see EM-1 | **The emulation build environment** (doc 13). VM gets 4 GB; model never runs in-guest |
| **T2 — dev desktop (target)** | 32 GB unified / 24–32 GB VRAM | M1/M2/M3 Pro/Max 32 GB, RTX 3090/4090 24 GB | **14B Q4/Q5** or 7B Q6 | **Primary shipping target**. Comfortable, fast, room for context |
| **T1 — laptop / small box** | 16 GB | M1 16 GB, 16 GB + RTX 3060 12 GB | **7–8B Q4** (~5–6 GB weights + ~2–4 GB KV) | Viable, interactive but slower; keep contexts small |
| **T0 — constrained** | 8 GB | old laptop | 3B Q4 (Qwen2.5-Coder-3B) | Runs Phase 0–1 with more loop iterations and lower success ceiling; **not recommended** as production target |

**Minimum spec (requirement F0-2 companion): 16 GB RAM, 64 GB storage, 4+ fast
cores. Recommended: 32 GB RAM + GPU/NPU offload.**

**18 GB M3 note (the current builder machine):** memory budget is macOS+agents
(~6–8 GB) + host llama-server 7B Q4 (~6 GB, Metal) + VM 4096 MB + slack. The
split-brain serving arrangement (model on host, harness in VM, endpoint
`http://10.0.2.2:8080`) is mandatory here — running the model inside the VM on
CPU-only would be 2–4× slower and blow the memory budget.

Memory math for 7B Q4_K_M on 16 GB: weights 4.7 GB + KV cache @ 8k ctx ≈ 1.5 GB +
runtime ≈ 7 GB → leaves headroom for gcc, busybox, agent processes. For 14B Q4:
~8.5 GB weights + KV ≈ 11 GB → tight on 16 GB, fine on 32 GB.

## 2. Model matrix (candidates, re-verify versions at build time)

| Model | Params | Q4 size | Code quality | Tool calls | Notes |
|---|---|---|---|---|---|
| **Qwen2.5-Coder-7B-Instruct** | 7.6B | ~4.7 GB | ★★★★ | native | **Phase-1 primary**; best small coder of its class |
| Qwen2.5-Coder-14B-Instruct | 14.7B | ~9 GB | ★★★★★ | native | T2 upgrade; better Phase-2 planning |
| Llama-3.1-8B-Instruct | 8B | ~4.9 GB | ★★★ | native | Generalist; good tool calling; weaker on code |
| DeepSeek-Coder-V2-Lite | 16B MoE (2.4B active) | ~9 GB | ★★★★ | partial | Fast inference (MoE); tool-call support verify |
| Gemma-2-9B-it | 9B | ~5.8 GB | ★★★ | manual format | No native tool-call format → needs harness JSON fallback |
| Qwen2.5-Coder-3B | 3B | ~1.9 GB | ★★ | native | T0 fallback model |
| Frontier (cloud, Phase 3+) | — | — | ★★★★★+ | native | Claude/GPT/Gemini class via bridge |

Quantization guidance: **Q4_K_M** default (quality/size sweet spot); Q5_K_M if RAM
allows; never Q2-class for code (quality collapse on syntax-heavy tasks).

Model artifact pinning: store SHA-256 of each GGUF in `/ai/models/manifest.json`;
verify at boot (F0-2).

## 3. Inference parameters (start points)

| Param | Phase 1 (build) | Chat (`ask`) | Note |
|---|---|---|---|
| temperature | 0.2 | 0.7 | low temp for code determinism |
| top_p | 0.9 | 0.9 | |
| context | 8192 | 4096 | small contexts = fast; doc 02 R6 |
| max_tokens (step) | 1024 | 512 | one tool call or one patch per step |
| seed | session-pinned | free | reproducibility for evals (N3) |

## 4. Serving configuration

`llama-server` flags (baseline):
```
llama-server -m /ai/models/qwen2.5-coder-7b-q4_k_m.gguf \
  --host 127.0.0.1 --port 8080 -c 8192 --mlock \
  --n-gpu-layers 99        # or 0 on CPU-only
  --threads <ncores-1>
```
Plus `--parallel 1` (single user). Harness probes `/health` with 30 s timeout.

## 5. Router policy (Phase 3, doc 07 §6 implements)

| Task class | Route | Fallback |
|---|---|---|
| Small code gen/patch, tool loop steps | local | (is the fallback) |
| Long-context (>6k) analysis | cloud | local, chunked |
| Novel large app (Phase 4 architecture) | cloud | local step-by-step with human review |
| Chat/UX | local | — |

Router config lives in `/ai/state/router.json`; the agent edits it; harness enforces
a floor: **local model always available offline** (N1).

## 6. Costs

- Phases 0–2: **$0 API** (fully local; N9).
- Phase 3+: optional pay-per-token via bridge; harness logs cloud usage per session
  for budget visibility (user story 13).
