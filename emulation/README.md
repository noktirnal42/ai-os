# Emulation development platform

This platform boots and runs AI OS inside an Alpine aarch64 virtual machine on
the host Mac. The beginner first-run launcher is `./emulation/start.sh`; the
lower-level lifecycle remains `emulation/vm.sh`.

Use `emulation/vm.sh` for every VM operation. Run commands from the repository root.
The host is Apple Silicon macOS; the guest is Alpine aarch64/musl with QEMU/HVF,
4 CPUs, 4 GiB RAM, a 20 GiB overlay, passwordless sudo for `ai`, and workspace `/ai`.

## Setup and operation

For the guided setup, install QEMU and Ollama, install a local Ollama model, then
run the launcher in macOS Terminal:

```sh
brew install qemu ollama
ollama pull qwen2.5-coder:3b
./emulation/start.sh
```

The launcher detects Ollama, picks the recommended model when present (otherwise
the first installed local model), prepares and boots the VM if necessary, syncs
the current AI OS console, and opens its TUI. It does not install Ollama or
download model weights automatically. If the Ollama CLI exists but its service
is stopped, the launcher starts that local service. See [the first-run guide](../docs/15-FIRST-RUN-AND-TUI.md).

For lifecycle control and debugging:

```sh
brew install qemu
emulation/vm.sh doctor
emulation/vm.sh fetch             # upstream SHA-512 is mandatory; cache is rechecked
emulation/vm.sh create            # new disk, dedicated SSH key, NoCloud seed
emulation/vm.sh boot && emulation/vm.sh wait
emulation/vm.sh status
emulation/vm.sh exec 'uname -m; cat /etc/os-release'
emulation/vm.sh stop && emulation/vm.sh snapshot clean
```

`wait` polls SSH and cloud-init within `WAIT_SSH_TIMEOUT` (300 seconds by default).
Failures are nonzero; inspect `vm.sh logs` or, when SSH works,
`vm.sh exec 'sudo cloud-init status --long'`. Firmware may print failed boot-device
probes before successfully booting Alpine. Use readiness and guest checks to
assess success. `boot --fg` attaches the serial console.

```sh
emulation/vm.sh boot && emulation/vm.sh wait
emulation/vm.sh push emulation/tests/smoke.c /ai/tmp/emulation-smoke.c
emulation/vm.sh exec 'cc -Wall -Wextra -Werror /ai/tmp/emulation-smoke.c -o /ai/tmp/emulation-smoke && /ai/tmp/emulation-smoke'
emulation/vm.sh pull /ai/tmp/emulation-smoke.c /tmp/emulation-smoke.c
emulation/vm.sh exec 'exit 37'      # host exit status is 37
emulation/vm.sh stop
emulation/vm.sh list-snapshots
```

Push/pull accept a host path and a guest path; neither implicitly deletes files.
Directory trailing slashes have ordinary rsync semantics. For multiple commands,
pass one quoted guest shell string. Non-login SSH does not load profile scripts;
source `/etc/profile.d/aios.sh` when the command requires the model environment.

## Checkpoints and recovery

Snapshots require an explicitly stopped VM. Duplicate tags and unknown rollback
tags fail; rollback never creates a checkpoint. Destruction, deleting checkpoints,
and rolling back past a tagged milestone require explicit human approval.
Do not run rollback commands copied from documentation without that authorization.

The default repaired disk is `artifacts/aios-dev.qcow2`, backed by
`artifacts/alpine-verified.qcow2`. **Keep both**: the overlay alone is not a backup.
The inherited `aios.qcow2` and `alpine-cloud.qcow2` are preserved, with checkpoint
`inherited-20261016` on the old disk. The repaired instance uses `seed-dev.iso`,
`seed-dev.d`, `dev_ed25519`, and `known_hosts-dev`. Do not edit artifacts by hand.

`vm.sh seed` regenerates the stopped development instance's seed and instance ID,
causing cloud-init provisioning to run again on its next boot. This is for bootstrap
repair; it is not a general software update workflow. Edit source on the host and
use push/exec for normal development. `create` refuses an existing disk.

## Configuration and optional model runtime

Defaults in `vm.conf` accept environment overrides. Guest user, hostname,
`AIOS_MODEL_URL`, and `AIOS_MODEL` are rendered into the seed at creation (or
explicit reseeding). The launcher prefers host Ollama on port 11434 when
available; otherwise the legacy llama-server endpoint is `http://10.0.2.2:8080`.
The guest reaches host loopback services through QEMU user networking. SSH is
forwarded only on `127.0.0.1:2222`.

A model is unnecessary for platform checks. For future inference work, install
`llama.cpp`, acquire and independently verify a GGUF, set `MODEL_FILE`, and run
`emulation/model-host.sh` in a separate terminal. It serves on host loopback using
Metal. The launcher does not download models. Real model loading/inference has
not been validated by this platform repair. Wi-Fi hardware and bare-metal
performance also require later hardware testing.

## Verification

```sh
python3 -m unittest discover -s emulation/tests -v
zsh -n emulation/*.sh
emulation/vm.sh doctor
emulation/tests/smoke.sh          # live VM must already be ready
```

Tests isolate CLI behavior with command doubles; live acceptance evidence is in
[VALIDATION.md](VALIDATION.md). Normative platform specification:
[docs/13-EMULATION-PLATFORM.md](../docs/13-EMULATION-PLATFORM.md).
