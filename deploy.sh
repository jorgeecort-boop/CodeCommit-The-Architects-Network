#!/usr/bin/env bash
set -euo pipefail

if command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  SUDO=""
fi

$SUDO apt update
$SUDO apt install -y docker.io git

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  $SUDO apt install -y docker-compose
  COMPOSE_CMD=(docker-compose)
fi

"${COMPOSE_CMD[@]}" --env-file .env.production up -d --build
