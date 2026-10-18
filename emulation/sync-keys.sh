#!/bin/zsh
# Sync provider API keys from the macOS Keychain into the guest /ai/secrets/.
# Key material never appears in output: it is piped straight through rsync-over-ssh.
set -euo pipefail
source "$(dirname "$0")/env.sh"

# name | keychain service | keychain account
ENTRIES=(
  "openrouter|com.openclaudecodex.desktop.provider-keys|openrouter"
  "ollama-cloud|com.openclaudecodex.desktop.provider-keys|ollama-cloud"
  "nvidia-nim|com.openclaudecodex.desktop.provider-keys|nvidianim"
)

synced=0; missing=0
for entry in "${ENTRIES[@]}"; do
  name="${entry%%|*}"; rest="${entry#*|}"
  svc="${rest%%|*}"; acct="${rest#*|}"
  key=""
  for attempt in {1..5}; do
    key="$(security find-generic-password -s "$svc" -a "$acct" -w 2>/dev/null || true)"
    if [[ -n "$key" ]]; then break; fi
    sleep 1
  done
  if [[ -z "$key" ]]; then
    print -- "  [skip] $name (no keychain entry: $svc/$acct)"
    missing=$((missing + 1)); continue
  fi
  tmp="$(mktemp)"
  printf '%s' "$key" > "$tmp"
  chmod 600 "$tmp"
  trap 'rm -f "$tmp"' EXIT
  "$EM_DIR/vm.sh" push "$tmp" "/ai/tmp/.key-$name" >/dev/null
  "$EM_DIR/vm.sh" exec "umask 077; mv /ai/tmp/.key-$name /ai/secrets/$name.key && chmod 600 /ai/secrets/$name.key"
  rm -f "$tmp"
  print -- "  [ok]   $name -> /ai/secrets/$name.key"
  synced=$((synced + 1))
done

print -- "Keychain sync complete: $synced synced, $missing missing."
