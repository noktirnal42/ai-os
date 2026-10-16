#!/bin/zsh
# emulation/doctor.sh — pre-flight for the AI OS emulator (doc 13 §AE-1).
set -euo pipefail
source "$(dirname "$0")/env.sh"
PASS=0; FAIL=0; WARN=0
ok()   { echo "  [ok]   $*"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
warn() { echo "  [warn] $*"; WARN=$((WARN+1)); }

echo "AI OS emulator doctor — host: macOS $(sw_vers -productVersion) $(uname -m)"

echo "[1] toolchain"
command -v "$QEMU_BIN" >/dev/null && ok "qemu: $($QEMU_BIN --version | head -1)" || bad "qemu-system-aarch64 missing (brew install qemu)"
qemu_fw >/dev/null && ok "edk2 firmware: $(qemu_fw)" || bad "edk2-aarch64-code.fd not found"
command -v qemu-img >/dev/null && ok qemu-img || bad qemu-img
command -v curl >/dev/null && ok curl || bad curl
command -v rsync >/dev/null && ok rsync || bad "rsync (brew install rsync)"
command -v hdiutil >/dev/null && ok hdiutil || bad hdiutil
command -v ssh >/dev/null && ok "ssh $(ssh -V 2>&1 | cut -d' ' -f1)" || bad ssh

echo "[2] resources"
GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
if [ "$GB" -ge 16 ]; then ok "RAM: ${GB}GB"; else warn "RAM ${GB}GB < 16 (VM_MEM_MB may need lowering)"; fi
FREE_GB=$(df -g "$REPO_ROOT" | tail -1 | awk '{print $4}')
[ "$FREE_GB" -ge 25 ] && ok "free disk: ${FREE_GB}GB" || warn "free disk ${FREE_GB}GB < 25"
if vm_running; then
  ok "VM owns configured port $SSH_PORT (pid $(vm_pid))"
elif lsof -iTCP:"$SSH_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  bad "port $SSH_PORT occupied by another process"
else
  ok "port $SSH_PORT free"
fi

echo "[3] accelerator"
if [ "$VM_ACCEL" = "hvf" ]; then
  sysctl -n kern.hv_support 2>/dev/null | grep -q 1 && ok "Hypervisor.framework supported" || bad "hvf unsupported; set VM_ACCEL=tcg"
fi

echo "[4] artifacts"
[ -f "$BASE_IMAGE_FILE" ] && ok "cloud image present" || warn "no image yet (vm.sh fetch)"
[ -f "$DISK_FILE" ] && ok "VM disk present" || warn "no VM disk yet (vm.sh create)"
[ -f "$SEED_ISO" ] && ok "seed ISO present" || warn "no seed yet (vm.sh create)"

echo "[5] model endpoint (host)"
if curl -fsS -m 2 "http://127.0.0.1:${MODEL_PORT}/health" >/dev/null 2>&1; then
  ok "HTTP health reachable on :$MODEL_PORT (model identity not verified)"
else
  warn "no model server on :$MODEL_PORT (optional; needed only for future inference)"
fi

echo; echo "result: $PASS ok, $WARN warn, $FAIL fail"
[ "$FAIL" -eq 0 ]
