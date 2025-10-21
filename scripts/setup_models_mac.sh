#!/usr/bin/env bash
set -euo pipefail

echo "=== macOS model setup (Ollama + optional HF cache) ==="
echo -n "Checking native Ollama at http://localhost:11434 ... "
curl -sf http://localhost:11434/api/version && echo "OK"

# Pull your text models
echo "Pulling text models:"
echo "  pulling mixtral:8x7b-instruct ..."
ollama pull mixtral:8x7b-instruct || true
echo "  pulling llama3.1:70b-instruct ..."
ollama pull llama3.1:70b-instruct || true

# Optional: pre-cache Qwen2-VL and DocOwl2 locally via HF (no container needed)
python3 - <<'PY'
import os
from huggingface_hub import snapshot_download
tok = os.getenv("HUGGINGFACE_HUB_TOKEN")
if tok:
    os.environ["HF_TOKEN"] = tok
    print("Caching Qwen2-VL-7B-Instruct ...")
    p = snapshot_download("qwen/Qwen2-VL-7B-Instruct", allow_patterns=["*.json","*.txt","*.safetensors","*.py"])
    print("HF cached:", p)
    print("Caching mPLUG/DocOwl2 ...")
    p = snapshot_download("mPLUG/DocOwl2", allow_patterns=["*.json","*.txt","*.safetensors","*.py"])
    print("HF cached:", p)
else:
    print("HUGGINGFACE_HUB_TOKEN not set; skipping HF cache.")
PY
echo "=== Setup complete. Ollama OpenAI endpoint: http://localhost:11434/v1 ==="
