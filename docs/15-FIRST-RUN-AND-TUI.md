# First run and interactive console

AI OS runs in an Alpine aarch64 virtual machine on the Mac. Start it with one
command from macOS Terminal at the repository root:

```sh
./emulation/start.sh
```

## What the launcher does

The launcher checks QEMU, Apple virtualization support, disk space, the model
service, and the VM artifacts. It downloads and verifies the Alpine image and
creates/boots the VM when those steps are needed. It then copies the current
console files into the guest and opens the TUI.

The launcher detects host Ollama on port 11434 and prefers the installed
`qwen2.5-coder:3b` model. If that model is absent, it selects an installed local
Ollama model. When no model is installed, it prints a command such as
`ollama pull qwen2.5-coder:3b` and exits. This avoids downloading several GB
without the operator choosing to do so. The optional llama-server endpoint on
port 8080 remains supported.

The selected endpoint, model name, and timeout are saved in
`/ai/state/model.json` (no credentials) so direct guest commands use the same
settings after the launcher exits.

Host prerequisites:

```sh
brew install qemu ollama
ollama pull qwen2.5-coder:3b
```

The launcher starts the Ollama service when the CLI is installed but the service
is stopped. The first launch also needs network access to retrieve the
checksum-verified Alpine guest image. Later starts reuse the guest and local
model. To inspect the emulator without launching the TUI, run
`emulation/vm.sh doctor` and `emulation/vm.sh status`.

## Use the console

The TUI has two modes, shown in its header:

- **Chat:** type a question and press Enter. This makes one model request and
  does not expose tools to that request.
- **Do:** press **F2**, describe a task, and press Enter. AI OS can use its
  bounded tools to work under `/ai`; the task is limited to 32 tool calls and
  15 minutes. Existing file, network, registry, and approval safeguards remain
  active.

The footer shows the active model and endpoint. While AI OS works, the status
line displays elapsed model wait; the conversation log shows tool activity,
command exit codes, completion, and errors. Model requests default to 300
seconds, configurable through `AIOS_MODEL_TIMEOUT` from 10 to 600 seconds.
`F1` opens help, **F2** switches modes, **Up/Down** scrolls, and **Ctrl-C** or
**Esc** exits. Stopping a task terminates its process group.

Useful actions:

```text
/help                 show the in-app guide
/chat                 return to Chat mode
/do                   switch to Do mode
/do build a small app  switch to Do and immediately start the task
/quit                 exit the console
```

Alternatively, from an already configured guest shell run `aios tui`.

## Important boundaries

The TUI is a terminal client, not a graphical desktop. Chat answers are model
output, not verified facts. Do mode shows tool activity and verification evidence
but does not guarantee every requested task succeeds. Review the result and the
session log under `/ai/state/sessions/`. The VM and model are development tools,
not a hardened environment for untrusted public users or production workloads.

If the TUI reports a model timeout, check `emulation/vm.sh status`, confirm that
the local Ollama service responds, and retry with a smaller task. The UI keeps
showing elapsed time during the request; a model timeout is now a visible error
instead of a silent terminal wait.
