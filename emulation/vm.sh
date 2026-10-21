#!/bin/zsh
# The only interface for driving the emulator. No AI OS implementation lives here.
set -euo pipefail
source "$(dirname "$0")/env.sh"
usage() {
  cat <<'HELP'
usage: vm.sh <command> [args]
  doctor | fetch | create | boot [--fg] | wait | status | logs | tui
  seed               regenerate provisioning seed (stopped development VM only)
  ssh [args...]       SSH to the development VM
  exec CMD [args...]  execute a remote shell command; preserves exit status
  tui                 start the AI OS interactive console with a local model
  push SRC DST       copy host SRC to guest DST (no implicit deletion)
  pull SRC DST       copy guest SRC to host DST (no implicit deletion)
  stop               orderly guest shutdown, then signal fallback
  snapshot TAG       create a new checkpoint; VM must be stopped
  rollback TAG       restore an existing checkpoint; VM must be stopped
  list-snapshots     list checkpoints; VM must be stopped
  destroy            delete development disk and seed, with confirmation
exit codes: 0 success, 2 usage, 3 timeout, 4 missing prerequisite, 5 running conflict
HELP
}
require_disk() { [ -f "$DISK_FILE" ] || die 'not created; run vm.sh fetch && vm.sh create' 4; }
require_running() { vm_running || die 'VM not running; run vm.sh boot && vm.sh wait' 4; }
require_stopped() { vm_running && die 'VM running; run vm.sh stop first' 5; return 0; }
cmd="${1:-}"; (( $# )) && shift
case "$cmd" in
  doctor) exec "$EM_DIR/doctor.sh" ;;
  fetch) exec "$EM_DIR/download-image.sh" ;;
  create|seed)
    (( $# == 0 )) || { usage; exit 2; }
    ensure_artifacts
    require_stopped
    if [[ "$cmd" == create ]]; then
      [ ! -e "$DISK_FILE" ] || die "disk exists: $DISK_FILE" 5
    else
      require_disk
      log "regenerating seed; cloud-init will reprovision this development instance"
    fi
    [ -s "$BASE_IMAGE_FILE" ] && [ -s "$BASE_IMAGE_FILE.sha512" ] || die 'run vm.sh fetch first (verified image required)' 4
    want="$(cat "$BASE_IMAGE_FILE.sha512")"
    got="$(shasum -a 512 "$BASE_IMAGE_FILE" | awk '{print $1}')"
    [ "$want" = "$got" ] || die 'base image checksum mismatch' 4
    pubkey="$(host_pubkey)" || die 'cannot prepare SSH identity' 4
    local_seed="$ARTIFACTS_DIR/seed-dev.d"
    mkdir -p "$local_seed"
    # Escape sed replacement metacharacters; reject multiline configuration values.
    render_value() { [[ "$1" != *$'\n'* ]] || return 1; print -r -- "$1" | sed 's/[&|\\]/\\&/g'; }
    sed -e "s|\${HOST_PUBKEY}|$(render_value "$pubkey")|g" \
        -e "s|\${MODEL_URL}|$(render_value "$(model_url_for_guest)")|g" \
        -e "s|\${MODEL_NAME}|$(render_value "$(model_name_for_guest)")|g" \
        -e "s|\${GUEST_USER}|$(render_value "$GUEST_USER")|g" \
        -e "s|\${GUEST_HOSTNAME}|$(render_value "$GUEST_HOSTNAME")|g" \
        "$EM_DIR/provision/user-data.template" > "$local_seed/user-data"
    print -r -- "instance-id: aios-dev-$(date +%s)" > "$local_seed/meta-data"
    rm -f "$SEED_ISO"
    hdiutil makehybrid -iso -joliet -default-volume-name CIDATA \
      -o "$SEED_ISO" "$local_seed" >/dev/null
    if [[ "$cmd" == create ]]; then
      qemu-img create -f qcow2 -b "$BASE_IMAGE_FILE" -F qcow2 "$DISK_FILE" "${VM_DISK_GB}G"
    fi
    if [[ "$cmd" == create && -f "$ARTIFACTS_DIR/known_hosts-dev" ]]; then
      ssh-keygen -R "[127.0.0.1]:$SSH_PORT" -f "$ARTIFACTS_DIR/known_hosts-dev" >/dev/null 2>&1
    fi
    log "$cmd complete: $DISK_FILE; next: vm.sh boot && vm.sh wait"
    ;;
  boot)
    (( $# == 0 )) || [[ $# == 1 && "$1" == --fg ]] || { usage; exit 2; }
    require_disk; require_stopped; ensure_artifacts
    [ -f "$SEED_ISO" ] || die 'seed ISO missing' 4
    FW="$(qemu_fw)" || die 'EDK2 firmware missing' 4
    lsof -iTCP:"$SSH_PORT" -sTCP:LISTEN >/dev/null 2>&1 && die "port $SSH_PORT busy" 5
    rm -f "$QEMU_PIDFILE"
    cpu=host; [[ "$VM_ACCEL" == tcg ]] && cpu=max
    QEMU_ARGS=(-machine virt -accel "$VM_ACCEL" -cpu "$cpu" -smp "$VM_CPUS" -m "$VM_MEM_MB"
      -bios "$FW" -drive "file=$DISK_FILE,format=qcow2,if=virtio"
      -drive "file=$SEED_ISO,format=raw,if=virtio,readonly=on"
      -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:${SSH_PORT}-:22"
      -device virtio-net-pci,netdev=net0 -pidfile "$QEMU_PIDFILE")
    display_args=(-display none)
    if [[ "$VM_DISPLAY" == cocoa ]]; then
      QEMU_ARGS+=(-device virtio-gpu-pci -device virtio-keyboard-pci -device virtio-tablet-pci)
      display_args=(-display cocoa)
    elif [[ "$VM_DISPLAY" != none ]]; then
      die "VM_DISPLAY must be none or cocoa" 2
    fi
    if [[ "${1:-}" == --fg ]]; then exec "$QEMU_BIN" "${QEMU_ARGS[@]}" -nographic; fi
    if [[ "$VM_DISPLAY" == cocoa ]]; then
      # -daemonize forks after Cocoa initializes and crashes on macOS, so run QEMU as a
      # background process instead. -pidfile still records the PID for vm.sh.
      nohup "$QEMU_BIN" "${QEMU_ARGS[@]}" -serial "file:$CONSOLE_LOG" "${display_args[@]}" \
        </dev/null >>"$CONSOLE_LOG.out" 2>&1 &
      disown
    else
      "$QEMU_BIN" "${QEMU_ARGS[@]}" -daemonize -serial "file:$CONSOLE_LOG" "${display_args[@]}" \
        </dev/null >>"$CONSOLE_LOG.out" 2>&1
    fi
    for i in {1..20}; do vm_running && break; sleep 0.5; done
    vm_running || die "QEMU failed; run vm.sh logs" 4
    log "VM started (pid $(vm_pid)); next: vm.sh wait"
    ;;
  wait)
    require_disk; require_running
    deadline=$((SECONDS + WAIT_SSH_TIMEOUT))
    log "waiting for SSH and completed provisioning (max ${WAIT_SSH_TIMEOUT}s)"
    while (( SECONDS < deadline )); do
      require_running
      if ssh_cmd true 2>/dev/null; then
        cloud_state="$(ssh_cmd 'sudo cloud-init status 2>/dev/null' 2>/dev/null || true)"
        if [[ "$cloud_state" == *'status: error'* || "$cloud_state" == *'status: degraded'* ]]; then
          die "provisioning failed: $cloud_state; use vm.sh exec 'sudo cloud-init status --long'" 4
        fi
        if [[ "$cloud_state" == *'status: done'* ]] && ssh_cmd 'test -f /ai/.provisioned' 2>/dev/null; then
          log 'VM ready'; exit 0
        fi
      fi
      sleep 2
    done
    die 'readiness timeout; use vm.sh logs for diagnostics' 3
    ;;
  ssh) require_running; exec ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" "$GUEST_USER@127.0.0.1" "$@" ;;
  exec)
    (( $# > 0 )) || { usage; exit 2; }
    require_running
    ssh_cmd "$@"
    ;;
  tui)
    require_disk; require_running
    [[ -t 0 && -t 1 ]] || die 'interactive console needs a real terminal; run emulation/start.sh from Terminal' 4
    [[ -n "${AIOS_MODEL_URL:-}" && -n "${AIOS_MODEL:-}" ]] || die 'AIOS_MODEL_URL and AIOS_MODEL must be set; run emulation/start.sh' 4
    remote_cmd="AIOS_MODEL_URL=${(q)AIOS_MODEL_URL} AIOS_MODEL=${(q)AIOS_MODEL} AIOS_MODEL_TIMEOUT=${(q)${AIOS_MODEL_TIMEOUT:-300}} /ai/bin/aios tui"
    exec ssh "${SSH_OPTS[@]}" -tt -p "$SSH_PORT" "$GUEST_USER@127.0.0.1" "$remote_cmd"
    ;;
  push|pull)
    (( $# == 2 )) || { usage; exit 2; }
    require_running
    if [[ "$cmd" == push ]]; then
      rsync -az -e "$(rsync_transport)" -- "$1" "$GUEST_USER@127.0.0.1:$2"
    else
      rsync -az -e "$(rsync_transport)" -- "$GUEST_USER@127.0.0.1:$1" "$2"
    fi
    ;;
  status)
    if ! vm_running; then log 'VM: stopped'; exit 0; fi
    log "VM: RUNNING (pid $(vm_pid))"
    if ! ssh_cmd true 2>/dev/null; then log 'SSH: unreachable (not ready)'; exit 3; fi
    ssh_cmd 'sudo cloud-init status; uptime; df -h /; id; ls /ai' || exit $?
    # Non-login SSH does not source /etc/profile.d; explicitly load guest config.
    ssh_cmd '. /etc/profile.d/aios.sh; printf "model: %s (%s) " "$AIOS_MODEL_URL" "${AIOS_MODEL:-local}"; if curl -fsS -m 2 "$AIOS_MODEL_URL/health" >/dev/null 2>&1 || curl -fsS -m 2 "$AIOS_MODEL_URL/api/version" >/dev/null 2>&1; then echo REACHABLE; elif curl -fsS -m 2 "http://10.0.2.2:'"$OLLAMA_PORT"'/api/version" >/dev/null 2>&1; then echo "Ollama reachable at host port '"$OLLAMA_PORT"' (run emulation/start.sh to configure this guest)"; else echo "UNREACHABLE (run emulation/start.sh for setup help)"; fi'
    ;;
  logs) tail -n 100 "$CONSOLE_LOG"; [ ! -f "$CONSOLE_LOG.out" ] || tail -n 20 "$CONSOLE_LOG.out" ;;
  snapshot|rollback|list-snapshots)
    require_disk; require_stopped
    if [[ "$cmd" == list-snapshots ]]; then qemu-img snapshot -l "$DISK_FILE"; exit; fi
    (( $# == 1 )) && [[ "$1" == [a-zA-Z0-9]* && "$1" != *[^a-zA-Z0-9_.-]* ]] || { usage; exit 2; }
    tag="$1"
    tags="$(qemu-img snapshot -l "$DISK_FILE" | awk 'NR>2 {print $2}')"
    if [[ "$cmd" == snapshot ]]; then
      print -r -- "$tags" | grep -Fxq -- "$tag" && die "snapshot already exists: $tag" 5
      qemu-img snapshot -c "$tag" "$DISK_FILE"
    else
      print -r -- "$tags" | grep -Fxq -- "$tag" || die "snapshot not found: $tag" 4
      qemu-img snapshot -a "$tag" "$DISK_FILE"
    fi
    log "$cmd '$tag' done"
    ;;
  stop)
    if ! vm_running; then log 'not running'; exit 0; fi
    pid="$(vm_pid)"
    ssh_cmd 'sudo poweroff' >/dev/null 2>&1 || true
    for i in {1..30}; do vm_running || break; sleep 1; done
    if vm_running; then warn "shutdown timeout; sending TERM to $pid"; kill "$pid"; fi
    for i in {1..10}; do vm_running || break; sleep 1; done
    vm_running && die 'QEMU has not exited; disk remains locked' 5
    rm -f "$QEMU_PIDFILE"; log stopped
    ;;
  destroy)
    require_stopped
    printf 'Delete %s and %s? [y/N] ' "$DISK_FILE" "$SEED_ISO"
    read -r ans || exit 2
    [[ "$ans" == y ]] || exit 0
    rm -f "$DISK_FILE" "$SEED_ISO"; log destroyed
    ;;
  *) usage; exit 2 ;;
esac
