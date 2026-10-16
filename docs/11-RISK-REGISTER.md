# 11 — Risk Register

Live document: review at every phase gate. Likelihood/Impact: H/M/L.

| # | Risk | L | I | Mitigation | Trigger / go-no-go |
|---|---|---|---|---|---|
| R1 | 7B model can't reliably complete Phase-1 tasks | M | H | Loop-based self-repair (doc 05 §2); smaller tasks; try 14B on T2; eval-driven task resizing | If E1 pass rate <50% after prompt iteration + model bump → **stop, re-scope** (Phase 1 shrinks to 3 apps) |
| R2 | Agent loop diverges (repeats, flails, burns budget) | H | M | Budgets (§8), repetition detector in harness (n≥4 identical tool calls → inject "change approach"), human present | Divergence in >20% of eval sessions → harness change, not prompt fiddling |
| R3 | Tool-call format flakiness (esp. non-native models) | M | M | Native tool-call models preferred; JSON-strict fallback (doc 05 §4); max-2-corrections rule | Format failures >5%/calls → switch model |
| R4 | Sandbox escape via agent-built code | L | H | seccomp+namespaces, no_new_privs, RO binds; audits at gates (G0-4, G1-4) | Any escape in probes → **hard stop**, fix before any network phase |
| R5 | Prompt injection from web content (Phase 2+) | M | H | Defense-in-depth (doc 09 §1): sandbox can't act on most injections; gates on destructive ops; data≠instructions rule; injection evals | Injection eval fail → restrict browsing to allowlisted domains |
| R6 | Secrets leak into logs/context | M | H | Hook-only key entry, redactor at emit, G3-3 grep CI | Any leak in grep → rotate key, fix redactor, re-run evals |
| R7 | Wi-Fi driver/firmware hell on target hardware | M | M | G0-3: human pre-verify once; keep USB-Ethernet fallback path | Phase 2 blocked >2 days → ship with Ethernet target |
| R8 | Scope creep (GUI, browser ambitions) in Phase 1 | H | M | Strict briefs, phase gates, this register reviewed weekly | Any Phase-4 item started before G2 → reject |
| R9 | Model supply / version drift breaks reproducibility | M | M | SHA-pinned GGUFs (F0-2), model-change protocol (doc 10 §3) | — |
| R10 | Human fatigue: reviewing everything | H | M | Review only: gate prompts, install diffs, session verdicts; evals carry the rest; checkpoints make review cheap (rollback over perfection) | — |
| R11 | Harness bugs corrupt `/ai` state | M | M | Checkpoint-before-session (automatic), manifests as registry source of truth, harness property tests | — |
| R12 | Cloud costs surprise | L | M | Budget caps in bridge (max calls/session), usage logging per session | — |
| R13 | LLM safety incident (agent writes malware-class code on request) | L | H | Policy in prompts (refuse harmful classes), human present every session v1, install review | Any incident → review board, tighten briefs |

**Escalation ladder for incidents:** pause session → rollback checkpoint → fix
harness/spec → re-run evals → resume. Never debug live in a dirty session.

## Go/No-Go summary

- **After G0-4 fails** → do not proceed to Phase 1 (sandbox first).
- **After E1 battery <50% twice** → re-scope Phase 1 (R1 trigger).
- **Any sandbox escape or secret leak** → network phases frozen until resolved.
