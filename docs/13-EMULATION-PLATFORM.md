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

In the emulator, the model runtime runs **on the macOS host** (Metal gives us ~2–4×
the VM's CPU-only speed), and the VM's harness reaches it at `http://10.0.2.2:8080`
(QEMU slirp always maps host → 10.0.2.2). On bare-metal targets the model runs
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
  + `/etc/profile.d/aios.sh` exporting `AIOS_MODEL_URL=http://10.0.2.2:8080`,
  done-marker file.
- `meta-data`: instance id.
- Model endpoint override file: user-data renders from `vm.conf` so switching
  endpoint = edit one line.

### EM-5 Optional host model server (`emulation/model-host.sh`)

- Uses installed `llama-server` and an explicitly selected GGUF (or the configured
  `MODEL_REPO_FILE` in `emulation/models/`). No model download runs automatically.
- Binds `127.0.0.1:8080`; QEMU user networking lets the guest reach the host at
  `10.0.2.2`. Set `AIOS_MODEL_URL` before creation to provision another endpoint.
- Real inference and pinned model acquisition are deferred until AI OS work.
  A health response establishes reachability, not model quality or identity.
- The VM lifecycle and C build/test smoke checks do not require a model server.

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
  model-host.sh        EM-5 host model server launcher
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
