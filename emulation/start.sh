#!/bin/zsh
# First-run launcher: find a host model, ready the VM, sync the console, enter it.
set -euo pipefail
source "$(dirname "$0")/env.sh"

fail() { print -u2 -- "\nAI OS setup: $*"; exit 1; }

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print -- "Usage: ./emulation/start.sh\n\nChecks a local model, prepares/boots the AI OS VM, syncs the current console, and opens the interactive TUI. Run it from macOS Terminal."
  exit 0
fi
[[ -t 0 && -t 1 ]] || fail "Run this from macOS Terminal so the interactive console can take over the screen."

print -- "AI OS first run — checking the Mac and emulator…"
"$EM_DIR/doctor.sh" || fail "Fix the failed prerequisite above, then run ./emulation/start.sh again."

host_url="${AIOS_MODEL_URL:-}"
model="${AIOS_MODEL:-}"
if [[ -z "$host_url" ]]; then
  if ! curl -fsS -m 15 "http://127.0.0.1:${OLLAMA_PORT}/api/version" >/dev/null 2>&1 && command -v ollama >/dev/null 2>&1; then
    model_log="${TMPDIR:-/tmp}/AIOS-Ollama-$(date +%s).log"
    print -- "Ollama is installed but stopped; starting its local model service…"
    nohup ollama serve >"$model_log" 2>&1 </dev/null &
    disown $!
    for attempt in {1..30}; do
      curl -fsS -m 2 "http://127.0.0.1:${OLLAMA_PORT}/api/version" >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  if curl -fsS -m 15 "http://127.0.0.1:${OLLAMA_PORT}/api/version" >/dev/null 2>&1; then
    host_url="http://127.0.0.1:${OLLAMA_PORT}"
  elif curl -fsS -m 3 "http://127.0.0.1:${MODEL_PORT}/health" >/dev/null 2>&1; then
    host_url="http://127.0.0.1:${MODEL_PORT}"
  else
    fail "No local model server found. Start Ollama, install a local model (recommended: ollama pull ${OLLAMA_MODEL}), then retry. AI OS does not download multi-gigabyte models without asking."
  fi
fi

guest_url="$host_url"
host_url="${host_url/10.0.2.2/127.0.0.1}"
guest_url="${guest_url/127.0.0.1/10.0.2.2}"
guest_url="${guest_url/localhost/10.0.2.2}"
[[ "$guest_url" =~ '^https?://[A-Za-z0-9.:-]+(/[A-Za-z0-9._~:/-]*)?$' ]] || fail "Unsupported model URL: $host_url. Use an HTTP(S) host endpoint reachable from the VM."

if [[ "$host_url" == "http://127.0.0.1:${OLLAMA_PORT}" || "$host_url" == "http://localhost:${OLLAMA_PORT}" || "$guest_url" == "http://10.0.2.2:${OLLAMA_PORT}" ]]; then
  print -- "Reading local Ollama model list (this can take a few seconds)…"
  tags="$(curl -fsS -m 30 "$host_url/api/tags")" || fail "Ollama did not return its local model list at $host_url within 30 seconds. Check Ollama and retry."
  if [[ -z "$model" ]]; then
    model="$(print -r -- "$tags" | python3 -c 'import json,sys; rows=json.load(sys.stdin).get("models",[]); names=[r.get("name","") for r in rows if int(r.get("size",0) or 0)>0]; preferred="qwen2.5-coder:3b"; print(preferred if preferred in names else (names[0] if names else ""))')"
  fi
  [[ -n "$model" ]] || fail "Ollama has no local model. Run: ollama pull ${OLLAMA_MODEL}"
  print -r -- "$tags" | python3 -c 'import json,sys; name=sys.argv[1]; names={r.get("name") for r in json.load(sys.stdin).get("models",[])}; sys.exit(0 if name in names else 1)' "$model" || fail "Model '$model' is not installed in Ollama. Run: ollama pull '$model'"
else
  if [[ -z "$model" ]]; then
    print -- "Reading model name from the OpenAI-compatible endpoint…"
    model_list="$(curl -fsS -m 20 "$host_url/v1/models")" || fail "Could not read $host_url/v1/models. Set AIOS_MODEL to the model name expected by this endpoint and retry."
    model="$(print -r -- "$model_list" | python3 -c 'import json,sys; rows=json.load(sys.stdin).get("data",[]); print(rows[0].get("id","") if rows else "")')"
  fi
  [[ -n "$model" ]] || fail "No model name was returned by $host_url/v1/models; set AIOS_MODEL explicitly."
fi

if [[ ! -s "$BASE_IMAGE_FILE" ]]; then
  print -- "Fetching and checksum-verifying the Alpine guest image…"
  "$EM_DIR/vm.sh" fetch
fi
if [[ ! -s "$DISK_FILE" ]]; then
  print -- "Creating the AI OS development VM…"
  "$EM_DIR/vm.sh" create
fi
if ! vm_running; then
  print -- "Starting the guest and waiting for first-boot provisioning…"
  "$EM_DIR/vm.sh" boot
  "$EM_DIR/vm.sh" wait
fi

print -- "Installing the current AI OS console in the guest…"
config_file="$(mktemp -t aios-model-config)"
trap 'rm -f "$config_file"' EXIT
python3 -c 'import json,sys; f=open(sys.argv[3],"w"); json.dump({"url":sys.argv[1],"model":sys.argv[2],"timeout_seconds":300},f); f.write("\n"); f.close()' "$guest_url" "$model" "$config_file"
"$EM_DIR/vm.sh" push "$config_file" /ai/tmp/model.json
"$EM_DIR/vm.sh" exec 'if [ ! -s /ai/state/model.json ]; then mv /ai/tmp/model.json /ai/state/model.json && chmod 600 /ai/state/model.json; else rm -f /ai/tmp/model.json; fi'
"$EM_DIR/vm.sh" push "$REPO_ROOT/ai/aios.py" /ai/bin/aios.py
"$EM_DIR/vm.sh" push "$REPO_ROOT/ai/aios_tui.py" /ai/bin/aios_tui.py
"$EM_DIR/vm.sh" push "$REPO_ROOT/ai/aios" /ai/bin/aios

export AIOS_MODEL_URL="$guest_url"
export AIOS_MODEL="$model"
export AIOS_MODEL_TIMEOUT="${AIOS_MODEL_TIMEOUT:-300}"
print -- "Model: $AIOS_MODEL"
print -- "Connecting to the AI OS console. Use F2 to switch between Chat and Do."
"$EM_DIR/vm.sh" tui
