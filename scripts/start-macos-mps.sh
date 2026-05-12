#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-.env.public.dev}"

cd "$ROOT_DIR"

docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.macos-mps.yml up -d --build --remove-orphans

"$ROOT_DIR/scripts/run-ollama-macos-mps.sh" &
OLLAMA_PID=$!

cleanup() {
  kill "$OLLAMA_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

"$ROOT_DIR/scripts/run-rag-macos-mps.sh"
