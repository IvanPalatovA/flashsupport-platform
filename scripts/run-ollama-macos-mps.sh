#!/usr/bin/env bash
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama CLI is not installed. Install Ollama for macOS first: https://ollama.com/download" >&2
  exit 1
fi

if lsof -nP -iTCP:11434 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 11434 is already in use."
  echo "If this is the Ollama desktop app, stop it first, then run this script again."
  echo "The project needs Ollama listening on 0.0.0.0:11434 so Docker containers can reach it."
  lsof -nP -iTCP:11434 -sTCP:LISTEN
  exit 1
fi

export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
exec ollama serve
