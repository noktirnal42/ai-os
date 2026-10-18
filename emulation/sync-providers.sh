#!/bin/zsh
# Write /ai/state/providers.json describing every known model provider.
# Only key files that exist in the guest are marked available.
set -euo pipefail
source "$(dirname "$0")/env.sh"

"$EM_DIR/vm.sh" exec 'python3 - <<"PY"
import json, os, pathlib

def has(p):
    try:
        return bool(pathlib.Path(p).read_text().strip())
    except OSError:
        return False

providers = {
    "nvidia-nim": {
        "name": "NVIDIA NIM",
        "url": "https://integrate.api.nvidia.com",
        "key_file": "/ai/secrets/nvidia-nim.key",
        "default_model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "models": [
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "meta/llama-3.2-90b-vision-instruct",
            "z-ai/glm-5.3-flash",
        ],
    },
    "ollama-cloud": {
        "name": "Ollama Cloud",
        "url": "https://ollama.com",
        "key_file": "/ai/secrets/ollama-cloud.key",
        "default_model": "gemma4:31b-cloud",
        "models": ["gemma4:31b-cloud"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "url": "https://openrouter.ai/api",
        "key_file": "/ai/secrets/openrouter.key",
        "default_model": "openrouter/free",
        "models": [
            "openrouter/free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "qwen/qwen3.8-27b:free",
        ],
    },
    "ollama-local": {
        "name": "Ollama (local)",
        "url": "http://10.0.2.2:11434",
        "key_file": None,
        "default_model": "qwen2.5-coder:3b",
        "models": ["qwen2.5-coder:3b", "qwen2.5-coder:7b"],
    },
}

out = {"schema_version": 1, "providers": []}
for pid, p in providers.items():
    out["providers"].append({
        "id": pid,
        "name": p["name"],
        "url": p["url"],
        "key_file": p["key_file"],
        "available": p["key_file"] is None or has(p["key_file"]),
        "default_model": p["default_model"],
        "models": p["models"],
    })

pathlib.Path("/ai/state/providers.json").write_text(json.dumps(out, indent=2) + "\n")
print("providers.json written")
PY'
