# Live model contract

AI OS keeps model hosting outside the guest. The guest reaches an OpenAI-
compatible endpoint through the emulated host gateway and receives only the
chat/tool protocol it needs.

## Smoke test

The repeatable check is:

```sh
AIOS_MODEL_URL=http://10.0.2.2:11434 \
AIOS_MODEL=qwen2.5-coder:3b \
/ai/src/ai/evals/live-model.sh
```

It verifies an exact text response, then asks the model to create a file through
`fs_write` and checks the resulting bytes. The script fails closed when either
environment variable is absent or the response/mutation differs.

The planned dedicated model host remains `http://10.0.2.2:8080`; Ollama on
`11434` is the current development provider. Provider choice is explicit so
model availability is never mistaken for an emulator guarantee.

For the guided beginner flow, run `./emulation/start.sh` from macOS Terminal.
It prefers a running host Ollama server, checks its installed local models,
chooses `qwen2.5-coder:3b` when available, readies the guest, and launches the
interactive TUI. If there is no local model, it tells the user how to install
one and exits without downloading weights automatically. See
[`15-FIRST-RUN-AND-TUI.md`](15-FIRST-RUN-AND-TUI.md).

The TUI makes the request wait visible and defaults each HTTP model request to
300 seconds (`AIOS_MODEL_TIMEOUT`, bounded to 10–600 seconds). This is a
latency allowance, not a guarantee that an endpoint or model will answer.

## Boundaries

- The model cannot access the host filesystem directly.
- Tool calls are logged under `/ai/state/sessions/`.
- `/ai` path policy and network gates remain in force for every call.
- Tool and time budgets bound a session even when a model repeats a request.
