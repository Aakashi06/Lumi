#!/bin/sh
# Graph ingestion needs no LLM. Start generation only for Ask Lumi.
set -eu
cd "$(dirname "$0")/.."
command -v llama-server >/dev/null || { echo 'Install llama.cpp: brew install llama.cpp'; exit 1; }
test -f data/models/generation.gguf || { echo 'Missing data/models/generation.gguf. See README.md.'; exit 1; }
if lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
  echo 'Port 8080 is already in use.'
  exit 1
fi
exec llama-server -m data/models/generation.gguf --alias Qwen3-4B-Instruct-2507 --host 127.0.0.1 --port 8080 -c 4096 -np 1 -ngl 99 -b 128 -ub 64 --no-warmup >> data/generation.log 2>&1
