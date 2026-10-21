# 13 — Emulation Platform: Research, Spec & Build Plan

**The development environment for AI OS is a virtual machine on the builder's
MacBook Pro (M3, 18 GB unified RAM), driven by mainstream coding agents.** Nothing
flashes to hardware until the system has been built and eval-passed in the emulator.
The emulator is a first-class subsystem of this repo (`emulation/`).

The emulator is now the active build target for AI OS. The repaired default
instance uses `aios-dev.qcow2`, `seed-dev.iso`, and a dedicated SSH identity.
The inherited `aios.qcow2` remains preserved at `inherited-20261016`.

---

## 1. Why emulator-first

1. **Iteration speed.** Snapshot → break it → rollback in seconds, vs. re-flashing.
2. **Agent-driven construction.** Coding agents (Claude Code, Codex CLI, Cursor, …)
   run on the host and operate the VM through one deterministic CLI. Reproducible,
   scripted, no GUI babysitting.
3. **Safety.** Mistakes happen inside a qcow2 file, not on hardware.
4. **Parity by design.** The VM runs the *same* target stack (Alpine aarch64, same
   packages, same `/ai` layout) so Phase 0–4 work transfers to bare metal nearly
   unchanged.

## 2. Virtualization research (Apple Silicon macOS, 2026)

| Option | Verdict | Why |
|---|---|---|
| **QEMU CLI + HVF acceleration** | **Chosen** | Fully scriptable/headless; `hvf` uses Apple Hypervisor.framework (near-native); aarch64 emulation of an aarch64 guest (no ISA translation penalty); we already have `qemu-system-aarch64` + EDK2 firmware installed; snapshot control (`qemu-img`) |
| UTM (GUI over QEMU/vz) | Rejected for automation | GUI-centric; fine as a fallback if HVF misbehaves |
| Apple Virtualization.framework (vz) directly (Lima-style) | Strong alternative | Fastest, but less scriptable control over serial/snapshots; QEMU wraps everything we need |
| Multipass / Lima / colima | Rejected | Container-cloud oriented; Alpine not first-class; hidden provisioning |
| Docker | Rejected | Not a VM; no kernel boundary; wrong fidelity for an OS project |
| Parallels/VMware | Rejected | Commercial, GUI, overkill |

**Guest OS:** Alpine Linux **aarch64 "cloud" image** (pre-installed qcow2, cloud-init
enabled, virt-optimized kernel image size varies by release). Chosen because provisioning is declarative
(cloud-init NoCloud seed) — no interactive `setup-alpine`, which is essential for
agent-driven, repeatable builds.

## 3. Resource plan on 18 GB (M3)

| Consumer | RAM | Notes |
|---|---|---|
| macOS + agents on host | ~6–8 GB | unavoidable base |
| **llama-server on HOST** (7B Q4 via Metal) | ~6–7 GB | GPU-accelerated on M3 — *not in the VM* |
| **AI OS VM** | 4096 MB (default) | Alpine + gcc + harness is light |
| headroom | ~1–2 GB | close other apps during eval runs |

**Key architectural decision — split-brain model serving (EM-1):**

In the emulator, the model runtime runs **on the macOS host** and the VM's
harness reaches it through the QEMU gateway `10.0.2.2`. The guided launcher
prefers an available Ollama endpoint on port 11434; the optional llama-server
configuration remains on port 8080. On bare-metal targets the model runs
*inside* the machine and the endpoint is `127.0.0.1:8080`.

Therefore: **the model endpoint is configuration, never an assumption**
(`AIOS_MODEL_URL` env / `/ai/state/model.json`). This one rule makes the emulation
↔ hardware transition a config change, and it is why the emulator can host the
entire Phase 1–4 build.

## 4. Emulation platform spec

### EM-1 VM definition (normative defaults, overridable via `emulation/vm.conf`)

| Item | Value |
|---|---|
| Arch / machine | aarch64, `-M virt`, CPU `host`, accel `hvf` |
| vCPU / RAM | 4 / 4096 MB |
| Disk | `artifacts/aios-dev.qcow2`, 20 GB, qcow2 (growpart on first boot) |
| Firmware | `/opt/homebrew/share/qemu/edk2-aarch64-code.fd` (UEFI) |
| Net | slirp user-mode; `hostfwd tcp:2222→22`; guest sees host at `10.0.2.2` |
| Console | serial → `artifacts/console.log` + foreground `-nographic` mode |
| Display | `VM_DISPLAY=none` (default, headless). `VM_DISPLAY=cocoa` adds a macOS window with `virtio-gpu-pci`, `virtio-keyboard-pci`, `virtio-tablet-pci`. Cocoa mode runs QEMU in the background, not with `-daemonize` (that fork crashes on macOS). |
| Seed | cloud-init NoCloud ISO (`CIDATA`), built with `hdiutil makehybrid` |
| User | `ai` (passwordless sudo; UID assigned by Alpine), dedicated SSH key `artifacts/dev_ed25519` |
| Bootstrap packages | git, gcc, make, musl-dev, curl, rsync, python3, openssh, e2fsprogs |

### EM-2 Lifecycle CLI (`emulation/vm.sh`) — the only interface agents use

```
vm.sh doctor        pre-flight: qemu, firmware, image, disk space, RAM budget
vm.sh fetch         download + checksum-verify Alpine aarch64 cloud image
vm.sh create        create qcow2 overlay + seed ISO from provision/ (refuses if disk exists)
vm.sh boot [--fg]   start VM headless (default) or foreground console
vm.sh wait          poll SSH + completed provisioning (overall deadline 300s)
vm.sh ssh [args]    interactive SSH into VM
vm.sh exec CMD...   run command in VM, stream output, exit code propagates   ← agents use this
vm.sh push SRC DST  rsync host→vm (/ai tree sync)
vm.sh pull SRC DST  rsync vm→host
vm.sh status        running? uptime, disk, mem, cloud-init state, model endpoint reachable?
vm.sh snapshot TAG  stop-safe snapshot via qemu-img (VM must be stopped)
vm.sh rollback TAG  restore snapshot (VM must be stopped)
vm.sh stop          guest poweroff; TERM fallback after 30 s, verifies exit
vm.sh destroy       delete disk + artifacts (requires confirm)
```

Exit codes are meaningful (0 ok, 2 usage, 3 timeout, 4 not-created) so agents can
branch on them. All commands are non-interactive except where confirmation is
inherent (`destroy`, `--fg`).

### EM-3 Agent integration contract (repo-root `AGENTS.md`)

Mainstream coding agents build AI OS by:
1. Reading `AGENTS.md` → learning `emulation/vm.sh` is the only VM surface.
2. Editing code on the host (repo checkout) → `vm.sh push /ai ...` → `vm.sh exec ...`
   to build/test inside the VM.
3. Never invoking `qemu-system-aarch64` directly; never hand-editing artifacts.
4. Using `vm.sh snapshot` at phase/step boundaries and `vm.sh rollback` on failure.

This keeps agent context small (one CLI), actions auditable (script wraps QEMU),
and the workflow identical across Claude Code / Codex / Cursor / opencode.

### EM-4 Provisioning (`emulation/provision/`)

- `user-data` (cloud-init): hostname `ai-os-emu`, user `ai` + host pubkey, packages
  (EM-1 table), `growpart`/resizefs, motd banner, runcmd writes `/ai/` skeleton
  + `/etc/profile.d/aios.sh` exporting the selected `AIOS_MODEL_URL`, model name,
    and a 300-second inference timeout,
  done-marker file.
- `meta-data`: instance id.
- Model endpoint override file: user-data renders from `vm.conf` so switching
  endpoint = edit one line.

### EM-5 Host model service and guided first run

- `emulation/start.sh` checks local Ollama on `127.0.0.1:11434` first, then the
  optional llama-server on `127.0.0.1:8080`. It selects an installed local model,
  prepares/boots the VM if needed, syncs the console, and opens the TUI.
- `emulation/model-host.sh` still runs an explicitly selected GGUF through
  `llama-server` on port 8080. No Ollama install or model-weight download runs
  automatically. Missing model instructions are printed before starting the UI.
- The running console receives the model URL/name explicitly, so an older VM seed
  pointing at port 8080 does not silently block the guided Ollama path.
- The guided live-model smoke test establishes protocol behavior, not model
  quality. A health response establishes reachability, not identity.
- The VM lifecycle and C build/test smoke checks do not require a model server.

The TUI supports Chat mode (one model answer without tools) and Do mode (a
bounded 32-tool, 15-minute task), displays session audit events and elapsed model
waits, and leaves the `/ai` and network gates unchanged. See the operator steps
and interaction contract in [the first-run guide](15-FIRST-RUN-AND-TUI.md).

### EM-6 Snapshots & artifacts

- `artifacts/` (gitignored): qcow2, seed-dev.iso, console.log, downloads.
- Snapshots: `qemu-img snapshot -c <tag>` — requires VM stopped; `vm.sh snapshot`
  refuses while running; explicitly stop first. Standard tags: `clean` (post-provision),
  `phase0-done`, `phase1-*`…
- Retain the overlay, its verified backing image, dedicated SSH identity, and
  provisioning seed. Recreate using fetch/create/boot/wait; duration depends on
  downloads and package mirrors. Destructive actions require human approval.

### EM-7 Fidelity gaps vs bare metal (honest ledger)

| Gap | Impact | Handling |
|---|---|---|
| No Wi-Fi hardware (slirp is Ethernet) | Phase 2 wpa_supplicant untestable in VM | In emulator, playbook runs the same *sequence* against eth0/DHCP; `net.json` carries `emulated: true`; real Wi-Fi validated at hardware bring-up (G0-3 gate stands) |
| Model in host, not VM | Harness endpoint differs | EM-1 config rule |
| No GPU in guest | n/a (model is on host) | — |
| slirp ≠ real NIC | Minor timing/MTU differences | Phase 2 live-net tests re-run on hardware |
| Perf ≠ hardware | Eval latency budgets recalibrated for emulator (documented multipliers) | doc 10 budget tables carry `emu:` variants |

The toolchain, musl, gcc, BusyBox, and `/ai` layout are intended to match the
future target. Kernel, package versions, hardware behavior, and any future
harness must be validated separately; byte-for-byte parity is not established.

## 5. Build plan (this deliverable)

```
emulation/
  README.md            operator + agent guide
  vm.conf              tunables (RAM, CPUs, ports, image URL, model)
  env.sh               shared shell helpers
  vm.sh                EM-2 CLI (the contract)
  doctor.sh            pre-flight checks
  download-image.sh    Alpine aarch64 cloud image fetch + SHA verify
  model-host.sh        optional llama.cpp host server
  start.sh             first-run Ollama/VM/TUI setup
  provision/
    user-data          cloud-init (EM-4)
    meta-data
  artifacts/           gitignored runtime state
```

Acceptance for the emulation subsystem itself:
- AE-1 `vm.sh doctor` passes on a clean M3 Mac with brew qemu installed.
- AE-2 `vm.sh fetch` verifies SHA-512 of the cloud image.
- AE-3 `create → boot → wait` produces an SSH-reachable Alpine VM <5 min on M3.
- AE-4 `vm.sh exec 'uname -m && cat /etc/os-release'` → `aarch64` + Alpine.
- AE-5 `vm.sh status` reports cloud-init done + model endpoint reachable (when
  `model-host.sh` running).
- AE-6 snapshot/rollback round-trips a marker file.
- AE-7 VM has `/ai` skeleton, `ai` user, `AIOS_MODEL_URL` exported at login.

## Repair notes (2026-10-16)

The implementation now fails closed if the upstream SHA-512 is missing or invalid,
records the resolved image URL and checksum, and rechecks cached images. SSH uses
a dedicated private key and `accept-new` host-key verification. `exec` calls the
SSH function normally (shell functions cannot be passed to `exec`); push/pull
construct the remote rsync path explicitly and never implicitly delete files.
Snapshot creation and restoration use distinct operations and reject duplicate
or unknown tags. Cloud-init no longer waits on itself, and readiness has a bounded
poll loop with explicit failure reporting. Status sources the guest endpoint
configuration because non-login SSH does not read profile scripts. Headless
startup uses QEMU daemon mode so it survives the invoking agent command. Alpine
uses an unlocked account with an unusable password hash and SSH password
authentication disabled, allowing public-key authentication without PAM.

The base image is an immutable dependency of the qcow2 overlay: retain it beside
the development disk. Copying the overlay alone is not a portable backup.

Acceptance evidence and remaining limits are recorded in
[`emulation/VALIDATION.md`](../emulation/VALIDATION.md).

---

## Change log

### 2026-10-20 — display device (spec change, flagged per AGENTS rule 8)

- **What changed:** `emulation/vm.conf` adds `VM_DISPLAY` (default `none`). `emulation/vm.sh boot`
  accepts `cocoa` and adds `virtio-gpu-pci`, `virtio-keyboard-pci`, and `virtio-tablet-pci`, with
  a macOS window. The default boot is unchanged.
- **Why:** phase 1 of the v2 desktop (`docs/18`) needs an on-screen compositor. Headless capture
  proved the desktop; the window proves it on screen.
- **Verified:** the guest sees `/dev/dri/card0` (driver `virtio_gpu`) and a 1280x800 virtual
  output, and a `sway` session with a `foot` terminal renders there (software renderer).
- **Not included:** input from the keyboard and tablet into the desktop (`libinput` setup), and
  any GL/EGL acceleration. The virtio GPU has no usable EGL driver in the guest yet.
- **Rollback:** boot with the default `VM_DISPLAY=none`. Snapshot `pre-display-device` holds the
  guest state before this change.

### 2026-10-20 — desktop input (follow-up to the display change)

- **What changed:** guest packages `eudev` and `wtype`; `udev` runs at boot; the `ai` user joins the
  `input` and `video` groups (set by `ai/desktop/setup.sh`). No change to `vm.sh` or the VM definition.
- **Verified:** sway sees `QEMU Virtio Keyboard` (keyboard) and `QEMU Virtio Tablet` (pointer), and
  keystrokes sent with `wtype` reach a `foot` terminal on the on-screen display.
- **Not verified:** physical key presses and mouse clicks made in the macOS window. The devices are
  connected, but the run did not include a live click or key press from the Mac.
- **Still not included:** GPU acceleration.

### 2026-10-20 — guest kernel upgrade attempt (reverted)

- **What was tried:** `apk upgrade linux-virt linux-virt-dev` in the guest, from 6.12.110 to 6.12.113,
  with headers installed to match. The goal was to let `kstage build` compile modules against the
  running kernel.
- **Result:** the VM did not boot the new kernel. The console showed `Mounting root: failed.` after
  the new kernel started. The package install itself succeeded.
- **Recovery:** `vm.sh rollback pre-kernel-upgrade`, taken before the upgrade, restored the guest to
  6.12.110. Desktop changes made earlier are kept; only changes after the snapshot were lost.
- **Not changed:** the VM definition in `emulation/vm.sh` and `vm.conf`. The guest still runs
  6.12.110, so `kstage build` still refuses until headers for that version are available or the
  kernel upgrade is fixed.
- **Next, if upgrading:** investigate the initramfs for 6.12.113 (root device and virtio modules)
  from a rescue shell, not by repeated reboots. Record the working kernel in this file.

### 2026-10-20 — guest kernel 6.12.113 (follow-up; the upgrade now works)

- **Cause of the earlier failure:** `apk upgrade linux-virt` replaced `/boot/vmlinuz-virt` but not
  `/boot/initramfs-virt`. The GRUB entry loads that initramfs with the new kernel, and it only held
  the 6.12.110 modules. The new kernel could not find the block driver, so root mount failed. This
  was read from the initramfs contents, not guessed.
- **Fix:** `sudo mkinitfs -o /boot/initramfs-virt 6.12.113-0-virt`. The old initramfs is kept as
  `/boot/initramfs-virt.6.12.110.bak`.
- **Result:** the VM boots 6.12.113 with root mounted, `/dev/dri/card0` is present, the desktop starts,
  and `kstage build aios_hello` builds and passes its test against the running kernel. The module was
  requested for a human load but not loaded.
- **Procedure for future kernel upgrades:** after `apk upgrade linux-virt linux-virt-dev`, run
  `sudo mkinitfs -o /boot/initramfs-virt <new-version>` before rebooting, then boot and check
  `uname -r`. Keep a `vm.sh snapshot` before the upgrade.
- **Open:** why the package post-install does not regenerate the initramfs on this image. Not
  investigated further.
- **VM definition:** unchanged in `emulation/vm.sh` and `vm.conf`.

### 2026-10-20 — autologin to the desktop on the console (guest configuration)

- **What changed in the guest:** `/etc/inittab` runs `/bin/login -f ai` on tty1 instead of a login
  prompt, and the ai user's profile starts `/ai/bin/desktop-session` (sway) on tty1. The serial console
  keeps its login prompt. No change to `emulation/vm.sh` or `vm.sh`'s VM definition.
- **Why:** after a reboot the QEMU window showed a small login prompt. The desktop now appears on boot.
- **Verified:** after a restart, sway runs on tty1 and the welcome terminal is on screen.
- **Note:** `ai/desktop/setup.sh` makes this change; a fresh guest needs the setup script run once.

