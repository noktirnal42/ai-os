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

## Fresh-provision check (2026-10-20)

A second VM was created from the Alpine base image, with separate artifacts and SSH port 2223, so the
main VM was untouched. Steps: `vm.sh create`, `vm.sh boot`, `vm.sh wait`, push `ai/desktop` and
`ai/kernel`, run `sh /ai/desktop/setup.sh` (exit 0). Its manifest is `manifest-fresh.json`.

Result: the desktop packages install from the repo, but the fresh VM is **not** equivalent to the release:

- Kernel: 6.12.110 in the fresh VM, 6.12.113 in the release. The kernel upgrade (and the initramfs
  regeneration in `docs/13`) is manual and not in `setup.sh`.
- Harness and apps: `/ai/bin/aios`, `aios.py`, the v1 apps, and their sources are missing. They come
  from the v1 provisioning and sync path (`start.sh`), not from `setup.sh`. There is no single
  provisioning entry point yet.
- Packages: 34 release-only (mostly kernel-build and crypto dependencies from the manual steps), 7
  fresh-only (version differences in curl, openssl, zlib).
- Files: `/ai/desktop/setup.sh` differs between the two, because the release guest was updated from an
  older copy of the repo. The manifest caught this drift, which is its job.

What this means: the release record is accurate for the candidate VM, but the repo does not yet
reproduce it. To make the release reproducible: add a provisioning script that installs the harness and
apps, does the kernel step (with initramfs regeneration), and pins the package set. Then run the fresh
check again.

The fresh VM is stopped. Its overlay files (`aios-fresh.qcow2`, `seed-fresh.iso`) remain in
`emulation/artifacts`; deleting them is a destructive step and needs your approval.

## Re-run with provision.sh (2026-10-20, second fresh VM)

`ai/release/provision.sh` was written and run in a new VM overlay (`aios-fresh2`, SSH 2224) from the base
image. The repo's `ai/` tree was packed on the host, pushed to `/ai/source`, and the script ran to
`PROVISION_DONE`, exit 0. It upgraded the kernel and regenerated the initramfs, installed the harness,
apps, and desktop, and wrote a manifest (`manifest-fresh2.json`).

What the comparison still shows, and why:

- **Kernel:** the manifest's `kernel` is the running kernel (6.12.110, because the new VM was not rebooted
  after the upgrade). The installed kernel is 6.12.113. Reboot after provisioning to match the release.
- **Extra files:** `._*` entries came from packing the tree on macOS. Pack with `COPYFILE_DISABLE=1 tar`.
- **Missing files:** the release VM holds v1 build-evaluation output in `/ai/apps` that the repo does not
  contain. Clean those before a real release, or exclude them from the manifest.
- **Changed files:** the release VM has older copies of some app manifests and `setup.sh`. The manifest
  caught this, which is its job.
- **Packages:** 33 release-only and 6 fresh-only, mostly from the kernel-build dependencies and a
  different crypto point release in the base image.

Net: the one-script provisioning path works end to end. The release VM is not yet a byte-for-byte rebuild
of it, for the reasons above. The next step is to fix the packing and manifest details, reboot after
provisioning, and then rebuild the release VM from the script instead of by hand.

The second fresh VM is stopped; its overlay and seed remain in `emulation/artifacts`.

