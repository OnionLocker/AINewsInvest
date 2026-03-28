#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/AINewsInvest/AINewsInvest"
VENV="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
DATE=$(date +%Y%m%d)

mkdir -p "$LOG_DIR"

echo "[$(date)] Starting daily pipeline..."

cd "$PROJECT_DIR"

$VENV main.py screen --market us_stock >> "$LOG_DIR/pipeline_${DATE}.log" 2>&1
$VENV main.py screen --market hk_stock >> "$LOG_DIR/pipeline_${DATE}.log" 2>&1

echo "[$(date)] Pipeline completed." >> "$LOG_DIR/pipeline_${DATE}.log"
