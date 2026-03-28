#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/AINewsInvest/AINewsInvest"
VENV="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
DATE=$(date +%Y%m%d)

mkdir -p "$LOG_DIR"

echo "[$(date)] Rebuilding stock pool..."

cd "$PROJECT_DIR"

$VENV main.py build-pool >> "$LOG_DIR/pool_${DATE}.log" 2>&1

echo "[$(date)] Stock pool rebuild completed." >> "$LOG_DIR/pool_${DATE}.log"
