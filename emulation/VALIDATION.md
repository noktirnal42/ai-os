# Emulation platform validation — 2026-10-16

Scope: the build/run/test VM only. No AI OS agent harness, applications, inference
loop, or bootstrap phases were implemented. The repository had no `.git` directory
at audit time; these changes are on disk and are not a Git commit.

## Environment and artifacts

- Host: Apple Silicon arm64, macOS 27.0.1, 18 GiB RAM; QEMU 11.1.1 with HVF.
- Guest: Alpine 3.22.6 aarch64, GCC 14.2.0, musl; user `ai` (assigned UID 1001),
  passwordless sudo. Root filesystem 18.7 GiB, approximately 17.6 GiB available.
- Default development disk: `emulation/artifacts/aios-dev.qcow2` (4 GiB RAM,
  4 vCPUs, 20 GiB virtual disk), backed by `alpine-verified.qcow2`.
- Image: `alpine-3.22.6-aarch64-uefi-cloudinit-r0.qcow2` from the configured
  official Alpine v3.22 cloud release directory. Fetch requires the upstream
  SHA-512 and records both URL and checksum alongside the base image.
- Verified SHA-512:
  `e7b58da6b3d122d17b78eece68dc4624aad9390e02428b9f16dcd78480ead324d24dc558c601a3a8a174061f23a173d17d334f807239808934a110ace7ea17ab`.
- Inherited `aios.qcow2` and `alpine-cloud.qcow2` were retained; old disk checkpoint
  `inherited-20261016` was created before changing the default instance.
- A second fresh disk, `firstboot-check.qcow2`, independently passed initial
  provisioning and the live smoke test at 1 GiB RAM on SSH port 2223. It is stopped
  and retained at checkpoint `firstboot-verified`.

## Defects repaired

- `exec` tried to execute a shell function as an external program.
- Push/pull lacked a remote rsync endpoint; transfers now quote individual SSH
  arguments correctly and do not implicitly delete destination files.
- Rollback first attempted snapshot creation; operations are now distinct.
  Unknown restore tags, duplicate snapshot tags, and running-disk operations fail.
- Cloud-init's final command waited for cloud-init itself, causing a deadlock.
- Alpine's locked account prevented SSH public-key login. Provisioning now uses
  an unlocked account with an unusable `*` password hash and SSH password
  authentication disabled. A dedicated VM identity avoids unrelated host keys.
- SSH host keys use scoped accept-new verification; a new instance clears only
  its own old host/port entry during creation.
- `vm_pid` always returned failure and did not verify process identity. It now
  validates the PID, QEMU process command, and configured disk.
- Agent command teardown killed background QEMU. Headless startup now uses
  QEMU daemon mode and survives between independent commands.
- Image discovery missed current upstream filenames. Fetch now matches them,
  requires valid SHA-512, rejects a mismatch, and rechecks cached content.
- Readiness previously had no provisioning deadline and reported incorrect error
  codes; it now polls with a deadline and reports cloud-init failures explicitly.
- Provisioned user/hostname/model endpoint are rendered from configuration;
  status loads the guest profile to report the provisioned endpoint.
- TCG selects CPU `max` instead of HVF-only CPU `host`. TCG execution is not live
  validated; the intended host uses HVF.

## Evidence

| Check | Result |
|---|---|
| `zsh -n emulation/*.sh emulation/tests/smoke.sh` | Passed |
| `python3 -m unittest discover -s emulation/tests -v` | 17 passed, including shell paths with spaces, daemon startup arguments, guest failure propagation, transfer direction/quoting, checkpoint operations, missing/malformed/mismatched checksums, and corrupt cache rejection |
| `vm.sh doctor` | No failures; absent optional model server is a warning |
| Verified image → create → boot → wait | Passed on a separate fresh instance with the corrected seed, within the configured 300-second readiness deadline |
| `sudo cloud-init status --long` | `status: done`, `errors: []`, `recoverable_errors: {}` |
| `sudo cloud-init schema --system` | Valid user-data and network-config |
| `vm.sh exec` architecture/toolchain/workspace checks | aarch64, Alpine 3.22.6, GCC 14.2.0, writable `/ai`, sudo works, secrets directory mode 700 |
| Live `emulation/tests/smoke.sh` | Host C source pushed to guest; strict-warning compilation and execution passed; pulled source matched byte-for-byte; guest exit 37 propagated to host |
| Host connectivity | Guest curl to `http://10.0.2.2:8080/health` returned the temporary fixture's JSON identifying itself as `emulation-network-test`, `inference:false`; fixture then stopped |
| Restart persistence | Marker and provisioning persisted across orderly stop/boot/wait; QEMU survived launcher completion |
| Checkpoint round-trip | Saved marker `before` at `emulation-smoke`, changed it to `after`, stopped, restored that same latest checkpoint, booted, verified `before`; no earlier milestone was crossed |

## Remaining boundaries

A temporary HTTP fixture proves networking only. No real GGUF was downloaded,
no model was loaded, and no inference was run. The optional llama-server launcher
is prepared for future use but still needs real-model validation. Firmware prints
unsuccessful boot-device probes before booting the guest; successful cloud-init,
SSH, build/run, and restart checks establish readiness. Wi-Fi, GPU access in the
guest, bare-metal hardware behavior, and target performance remain future work.

The default VM is left stopped at checkpoint `clean`, after removing smoke-test
files from `/ai/tmp`. Resume with:

```sh
emulation/vm.sh boot && emulation/vm.sh wait
emulation/tests/smoke.sh
```

Only `emulation/vm.sh` was used to operate guests, QEMU, images, and checkpoints.
Do not remove backing images or private keys, delete checkpoints, destroy guests,
or roll back past a tagged milestone without the required human approval.
