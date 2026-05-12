#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-.env.public.dev}"

cd "$ROOT_DIR"
exec docker compose --env-file "$ENV_FILE" -f docker-compose.yml up -d --build --remove-orphans
