# AI OS v2 — release candidate (emulator)

Status: **candidate.** Built and checked in the emulator only. Not a bare-metal or USB image.

## What this release contains

- Guest: Alpine 3.22 aarch64, kernel `6.12.113-0-virt` (see `manifest.json`).
- Desktop: sway on tty1 with autologin, foot, fuzzel, the launcher and app menu, a top bar, and window
  and workspace keys (`ai/desktop`).
- Agent: `aios` harness with Chat and Do modes, the console, and the chat window (`ai/`).
- Apps: calc, fileutils, jobs, aed, ask, net, tasks, selftest, aipkg, wbrowse, mail (GTK window), notes
  (via the tutorial, not installed by default).
- Safety and control: approval gates for installs and removals; a narrow-only policy file; the
  activity window; desktop checkpoints; staged kernel modules with a human load step (`docs/19`).

## Snapshot and checksum

- VM snapshot tag: `release-candidate-v2` (taken with the VM stopped).
- Disk: `emulation/artifacts/aios-dev.qcow2`, SHA-256
  `54db821c8d092a18ab42ab25f01767e5c784851ce958b0bebcac5fbadca1ed4b` (read at snapshot time).
- The disk file is generated and not committed. Re-check with the command below after any change.

```bash
shasum -a 256 emulation/artifacts/aios-dev.qcow2
```

## What "reproducible" covers, and what it does not

Covered:
- The packages and their exact versions are recorded in `manifest.json`.
- The desktop, tools, and app sources are in the repo; `ai/desktop/setup.sh` installs the guest parts.
- The manifest hashes every repo-managed file in the guest, so a drift shows as a changed hash.

Not covered yet:
- A fresh VM has not been built from scratch and checked against the manifest. That needs a full
  provisioning run (`vm.sh create`, boot, `setup.sh`), which is the next step before calling this a
  release rather than a candidate.
- The guest's `/ai/apps` also holds build-evaluation output from v1 runs; it is in the manifest but
  should be cleaned before a real release.
- The kernel upgrade procedure (`docs/13`) is manual: initramfs regeneration must be done by hand.

## Procedure

1. `emulation/vm.sh stop && emulation/vm.sh snapshot <tag>`.
2. Boot and run `sh /ai/release/manifest.sh`, then `emulation/vm.sh pull /ai/release/manifest.json ai/release/manifest.json`.
3. Record the snapshot tag and the disk SHA-256 here.
