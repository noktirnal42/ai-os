# AI OS bootstrap validation — 2026-10-16

The first AI OS slice was built and tested inside the validated Alpine aarch64
emulator. This is a Python reference harness plus the first Phase 1 utilities.

Guest evidence:

* `make test`: 5 harness tests passed.
* `make calc-test`: calculator acceptance passed with `ALL PASS` under Alpine GCC.
* `calc "2^10"`: printed `1024`.
* `make fileutils-test`: file utilities acceptance passed with `FILEUTILS ALL PASS`.
* `make jobs-test`: job runner start/list/log/kill acceptance passed.
* `make aed-test`: line editor save, search, delete, undo, and quit acceptance passed.
* `make ask-test`: offline `ask` command acceptance passed.
* Interactive calculator input `x = 5`, `x * 2`, `quit` returned `10`.
* `/ai/bin/aios run --offline "run the offline bootstrap smoke"`: returned the
  explicit `[offline] model disabled` response and wrote a JSONL verdict under
  `/ai/state/sessions/`.
* Registry installs were performed through the harness registry tool. `/ai/state/registry.json`
  contains `calc`, `fileutils`, `jobs`, `aed`, and `ask`, each with `tests_pass: true`
  and manifest paths.
* The harness fake-model test drove a real `fs_write` tool call, verified the file
  mutation, then completed the session with an assistant message.
* Live inference through the host Ollama OpenAI-compatible endpoint succeeded:
  `AIOS_MODEL_URL=http://10.0.2.2:11434 AIOS_MODEL=qwen2.5-coder:3b /ai/bin/aios ask
  "Reply with exactly LIVE_MODEL_OK"` returned `LIVE_MODEL_OK`.
* The same live model generated a JSON tool call which the harness parsed and
  executed. `/ai/tmp/live-model-two.txt` contained `LIVE_TWO_TOOL_OK`, and the
  session JSONL recorded successful `fs_write` and `shell` tool results.
* `evals/run.sh --phase 1 --repeat 2` passed all six Phase 1 tasks twice and
  appended the results to `/ai/state/evals.csv`.
* `evals/sandbox-probes.py` passed secret, protected-path, network, and shadow-file
  denial probes. Phase 0/1 shell networking is disabled unless explicitly enabled
  in the process environment.

The harness enforces `/ai` path policy, rejects `/ai/secrets`, caps shell output at
4 KiB, bounds shell timeouts, rejects a Phase 0 destructive-command subset, keeps
session logs append-only JSONL, and implements checkpoint and registry tools. Its
model client speaks the OpenAI-compatible `/v1/chat/completions` endpoint exposed
by the planned host model server.

The VM was checkpointed as `phase1-foundation-apps-v2` before this slice. The
next checkpoint is taken after the evaluation and probe suite and becomes the
current Phase 1 baseline. Resume with:

```sh
emulation/vm.sh boot && emulation/vm.sh wait
emulation/vm.sh exec '/ai/bin/calc "2^10"'
```

The default endpoint remains `http://10.0.2.2:8080` for the planned dedicated
model host and is intentionally optional. The current live test path uses the
host Ollama service at `http://10.0.2.2:11434` with `qwen2.5-coder:3b`; the endpoint
and model are process overrides, so the guest default configuration is unchanged.
The harness accepts both native OpenAI `tool_calls` and the fenced JSON tool-call
format emitted by this model. Model behavior is still bounded by the session's
tool and time budgets; a model can emit an invalid follow-up tool request, which
is logged as a tool error without escaping the workspace policy.
