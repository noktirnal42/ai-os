#!/bin/zsh
# emulation/model-host.sh — run the LLM on the macOS HOST (Metal), for the VM (EM-1/EM-5).
# The guest harness reaches it at http://10.0.2.2:8080 via slirp.
set -euo pipefail
source "$(dirname "$0")/env.sh"

SERVER=""
for c in llama-server /opt/homebrew/bin/llama-server /usr/local/bin/llama-server; do
  command -v "$c" >/dev/null 2>&1 && { SERVER="$(command -v $c)"; break; }
done
if [ -z "$SERVER" ]; then
  command -v ollama >/dev/null 2>&1 && {
    warn "llama.cpp not found; ollama detected but not wired (doc 02 R2 prefers llama-server)."
    warn "Install with: brew install llama.cpp   then re-run."
    exit 4
  }
  die "llama-server not found. Install: brew install llama.cpp"
fi

MODEL="${MODEL_FILE:-$MODEL_DIR/$MODEL_REPO_FILE}"
MODEL="$(absp "$MODEL")"
if [ ! -f "$MODEL" ]; then MODEL=""; fi

if [ -z "$MODEL" ]; then
  cat >&2 <<EOF
No model file in $MODEL_DIR. Fetch one (SHA-record it in $MODEL_DIR/manifest):
  mkdir -p $MODEL_DIR
  curl -L -o $MODEL_DIR/$MODEL_REPO_FILE \
    "https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_REPO_FILE"
  shasum -a 256 $MODEL_DIR/$MODEL_REPO_FILE >> $MODEL_DIR/manifest
EOF
  exit 4
fi

if curl -fsS -m 2 "http://127.0.0.1:${MODEL_PORT}/health" >/dev/null 2>&1; then
  log "model server already live on :$MODEL_PORT"; exit 0
fi

log "serving $(basename "$MODEL") on 127.0.0.1:$MODEL_PORT (Metal) — guest endpoint: $(model_url_for_guest)"
exec "$SERVER" -m "$MODEL" --host 127.0.0.1 --port "$MODEL_PORT" \
  -c 8192 --mlock --parallel 1 -ngl 99
