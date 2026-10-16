# Contributing to AI OS

AI OS is an emulator-first research project. Contributions should leave the
system more observable, more reproducible, and safer to extend.

## Before opening a change

1. Read [AGENTS.md](AGENTS.md) and the relevant documents under `docs/`.
2. Keep VM interaction behind `emulation/vm.sh`; never edit emulator artifacts.
3. Run the focused test target, then `make -C ai test` and the relevant evals.
4. Update `ai/VALIDATION.md` when behavior or evidence changes.

## Pull requests

Explain the user-visible behavior, the safety boundary, and the exact commands
used to validate it. Small, focused pull requests are easier to review and
revert. Do not include model weights, VM disks, secrets, or generated runtime
state.

## Good first contributions

* Add a deterministic Phase 1 app with a manifest and acceptance test.
* Improve evaluator coverage with a reproducible fixture.
* Document a VM workflow or failure mode with evidence.
* Harden a tool boundary without widening its capabilities.
