#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Weekly automated update — used by cron (see install_cron.sh).
# Safe under overlap: a lock file prevents two concurrent runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/logs/.update.lock"
LOG="$ROOT/logs/update_weekly.log"
PY="${PYTHON:-python3}"

mkdir -p "$ROOT/logs"

# ---- overlap protection ----
if [ -d "$LOCK" ]; then
    echo "[$(date -u '+%F %T')Z] another update is still running — skipping this run" >> "$LOG"
    exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
mkdir "$LOCK"

echo "[$(date -u '+%F %T')Z] ===== weekly update started =====" >> "$LOG"
cd "$ROOT"
"$PY" update_data.py --full >> "$LOG" 2>&1 || {
    echo "[$(date -u '+%F %T')Z] update FAILED (exit $?)" >> "$LOG"
    exit 1
}
echo "[$(date -u '+%F %T')Z] ===== weekly update finished =====" >> "$LOG"
