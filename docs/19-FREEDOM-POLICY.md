# 19 — Freedom policy (v2, first slice)

Status: implemented for write roots and the activity window. Kernel-change staging and
checkpoint rollback are not built yet (see `docs/18` §5).

## What the policy controls

`/ai/policy.json` (default in `ai/desktop/policy/policy.json`, installed by `ai/desktop/setup.sh`)
lists the directories the agent may write to.

- **Narrow only.** A requested root is kept only if it lies inside a built-in root (`apps`,
  `lib`, `bin`, `state`, `tmp`, `out` under `/ai`). A policy cannot widen writes, so a request
  for `/` or `/etc` is ignored and recorded in the session's `policy` event.
- **Fail closed.** A malformed file, or one without a `write_roots` list, disables writes.
- **Missing file.** The built-in roots apply.
- **Not writable by the agent.** `/ai` is not a write root, so the agent cannot change its own policy.

Each session writes a `policy` event to its audit log with the roots in force.

## What it does not control yet

- Reads (`READ_ROOTS`) are still the built-in set.
- Network: still gated by `AIOS_ALLOW_NETWORK` and the allowlist, not by the policy.
- Kernel modules: no staging yet. Planned: build in a sandbox, test in the emulator, and ask
  before loading.

## Activity window

`Alt+g` opens `/ai/bin/activity`. It shows the write roots in force and the most recent audit
events from all sessions, with tool arguments never shown. It only reads the logs.

## Desktop checkpoints

`checkpoint` (`ai/desktop/bin/checkpoint`, installed as `/ai/bin/checkpoint`):

- `checkpoint create TAG` saves apps, bin, lib, desktop, the policy, and the foot and fuzzel configs
  to `/ai/checkpoints/desktop/TAG.tar.gz`, with a SHA-256 and a time stamp.
- `checkpoint rollback TAG` checks the checksum, saves the current state first as
  `pre-rollback-<time>`, then replaces those directories with the saved copy. It asks for a yes
  unless `-y` is given.
- It does not touch `/ai/state` (sessions, mail, notes, models), `/ai/secrets`, or the v1
  checkpoints.

Verified in the guest: a marker file added after `t2` was gone after the rollback, `aios` still
worked, a bad tag was refused, and the pre-rollback archive held the marker.

Limit: a rollback removes files added after TAG in the restored directories. The
pre-rollback checkpoint is the way back from that.

## Kernel-change staging (`kstage`)

`ai/kernel/bin/kstage`, installed as `/ai/bin/kstage`. The flow for a kernel module:

1. `kstage build NAME` compiles the source in `/ai/kernel/src/NAME` in a separate build directory
   against the running kernel's headers, then runs the module's acceptance test (`tests/run.sh`),
   which checks the module's identity and that it matches the running kernel. It does not load it.
2. `kstage request NAME` records a load request (path, SHA-256, vermagic) only after a passing
   build and test, and only for the running kernel.
3. `kstage load NAME` loads the module only if the file still matches the request hash and a
   human answers yes. Every decision goes to `/ai/state/kernel.log`.
4. `kstage unload NAME` unloads it, and the action is logged.

The agent can run steps 1 and 2. Step 3 needs a human at a terminal.

**Current blocker (2026-10-20):** the guest runs kernel `6.12.110-0-virt`, and the package
repository now offers `linux-virt-dev` 6.12.112. Installing that would give headers that do not
match the running kernel, so `kstage build` refuses with a clear message (exit 3). Two ways out,
both needing a decision: upgrade the guest kernel to match the headers (a reboot and a change to
the VM, to be flagged in `docs/13`), or wait until the repository carries headers for 6.12.110.
Verified so far: the refusal paths and the human gate (declined, and a changed file refused). No
module has been built or loaded.

