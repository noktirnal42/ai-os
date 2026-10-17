#!/bin/zsh
# emulation/env.sh — shared helpers. Source from other scripts; not run directly.
set -euo pipefail

EM_DIR="${${(%):-%N}:A:h}"
REPO_ROOT="$(dirname "$EM_DIR")"
source "$EM_DIR/vm.conf"

# absolute paths (relative values in vm.conf are relative to emulation/)
absp() { case "$1" in /*) echo "$1";; *) echo "$EM_DIR/$1";; esac; }
ARTIFACTS_DIR="$(absp "${ARTIFACTS_DIR#emulation/}")"
DISK_FILE="$(absp "${DISK_FILE#emulation/}")"
SEED_ISO="$(absp "${SEED_ISO#emulation/}")"
CONSOLE_LOG="$(absp "${CONSOLE_LOG#emulation/}")"
QEMU_PIDFILE="$(absp "${QEMU_PIDFILE#emulation/}")"
MODEL_DIR="$(absp "${MODEL_DIR#emulation/}")"
BASE_IMAGE_FILE="$(absp "$BASE_IMAGE_FILE")"
SSH_KEY_FILE="$(absp "$SSH_KEY_FILE")"

QEMU_BIN="${QEMU_BIN:-qemu-system-aarch64}"
QEMU_FW_CANDIDATES=(
  /opt/homebrew/share/qemu/edk2-aarch64-code.fd
  /usr/local/share/qemu/edk2-aarch64-code.fd
)
SSH_OPTS=(-F /dev/null -i "$SSH_KEY_FILE" -o IdentitiesOnly=yes
          -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$ARTIFACTS_DIR/known_hosts-dev"
          -o LogLevel=ERROR -o ConnectTimeout=5 -o BatchMode=yes
          -o ServerAliveInterval=5 -o ServerAliveCountMax=2)

log()  { printf '\033[1;36m[aios-emu]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[aios-emu]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[aios-emu] ERROR:\033[0m %s\n' "$1" >&2; exit "${2:-1}"; }

ensure_artifacts() { mkdir -p "$ARTIFACTS_DIR" "$MODEL_DIR"; }

qemu_fw() {
  for f in "${QEMU_FW_CANDIDATES[@]}"; do [ -f "$f" ] && { echo "$f"; return 0; }; done
  return 1
}

vm_pid() {
  local pid args
  [ -s "$QEMU_PIDFILE" ] || return 1
  pid="$(cat "$QEMU_PIDFILE")"
  [[ "$pid" == <-> ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  args="$(ps -p "$pid" -o command=)" || return 1
  [[ "$args" == *qemu-system-aarch64* && "$args" == *"$DISK_FILE"* ]] || return 1
  print -r -- "$pid"
}
vm_running() { vm_pid >/dev/null; }
ssh_cmd() { ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" "$GUEST_USER@127.0.0.1" "$@"; }
rsync_transport() { print -r -- "ssh ${(j: :)${(@qq)SSH_OPTS}} -p $SSH_PORT"; }
host_pubkey() {
  if [ ! -f "$SSH_KEY_FILE" ]; then
    ssh-keygen -t ed25519 -N "" -f "$SSH_KEY_FILE" -q || return
  fi
  ssh-keygen -y -P "" -f "$SSH_KEY_FILE"
}

model_url_for_guest() {
  if [[ -n "${AIOS_MODEL_URL:-}" ]]; then
    print -r -- "$AIOS_MODEL_URL"
  elif curl -fsS -m 2 "http://127.0.0.1:${OLLAMA_PORT}/api/version" >/dev/null 2>&1; then
    print -r -- "http://10.0.2.2:${OLLAMA_PORT}"
  else
    print -r -- "http://10.0.2.2:${MODEL_PORT}"
  fi
}
model_name_for_guest() {
  if [[ -n "${AIOS_MODEL:-}" ]]; then
    print -r -- "$AIOS_MODEL"
  elif curl -fsS -m 2 "http://127.0.0.1:${OLLAMA_PORT}/api/version" >/dev/null 2>&1; then
    print -r -- "$OLLAMA_MODEL"
  else
    print -r -- "local"
  fi
}
