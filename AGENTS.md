# AGENTS.md — contract for coding agents working on AI OS

The development environment is a
QEMU/HVF Alpine aarch64 VM on the host Mac. **The VM is driven exclusively through
`emulation/vm.sh`.** Read `docs/13-EMULATION-PLATFORM.md` for the full spec.

## Rules

1. **Only interface:** `emulation/vm.sh <cmd>` — never call `qemu-system-aarch64`,
   `qemu-img`, or raw `ssh -p 2222` directly. Never hand-edit `emulation/artifacts/`.
2. **Exec pattern:** edit code in the repo checkout on the host, then
   `emulation/vm.sh push <src> <dst>` and `emulation/vm.sh exec '...'` to build/test
   inside the VM. `exec` exit codes propagate — branch on them.
3. **VM state:** if `vm.sh status` shows the VM stopped, run
   `vm.sh boot && vm.sh wait` before `exec` (or report and stop if boot fails twice).
4. **Checkpoints:** run `vm.sh stop && vm.sh snapshot <tag>` at meaningful
   milestones; on failure, prefer `vm.sh rollback <tag>` over manual repair.
5. **Guest facts:** user `ai` (passwordless sudo), workspace `/ai`, model endpoint
   `$AIOS_MODEL_URL` (default `http://10.0.2.2:8080`), guest arch aarch64/musl.
6. **Destructive ops** (`vm.sh destroy`, deleting snapshots, `rollback` past a
   tagged milestone) require explicit user approval — ask first.
7. **Do not** start long-running VM work without the model server when a task needs
   LLM inference (`emulation/model-host.sh`, check with `vm.sh status`).
8. Spec changes go in `docs/`; never edit `docs/` specs silently — flag the change.

## Quick reference

```
vm.sh doctor|fetch|create|boot|wait|ssh|exec|push|pull|status|snapshot|rollback|stop|destroy
```

Guest reaches host at `10.0.2.2`; host reaches guest SSH at `127.0.0.1:2222`.
