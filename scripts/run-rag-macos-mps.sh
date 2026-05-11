#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="$ROOT_DIR/services/RAG Engine"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

cd "$SERVICE_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11 is required for RAG Engine. Install it or run with PYTHON_BIN=/path/to/python3.11." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

export RAG_ENGINE_ENV="${RAG_ENGINE_ENV:-dev}"
export APP_PORT="${APP_PORT:-18080}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://flashsupport_dev:flashsupport_dev@localhost:5432/flashsupport_dev}"
export LLM_RUNTIME_URL="${LLM_RUNTIME_URL:-http://localhost:8100}"
export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-mps}"
export EMBEDDING_MODEL_STORAGE_DIR="${EMBEDDING_MODEL_STORAGE_DIR:-var/embedding-models}"

python - <<'PY'
import torch

print("torch cuda available:", torch.cuda.is_available())
print("torch mps available:", torch.backends.mps.is_available())
PY

exec uvicorn main:app --app-dir src --host 0.0.0.0 --port "$APP_PORT"
