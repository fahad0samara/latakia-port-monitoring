#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Install the weekly cron job that keeps the Latakia port monitor up to date.
#
#   bash scripts/install_cron.sh          # install (idempotent)
#   bash scripts/install_cron.sh --remove # remove the job
#
# Schedule (default): every Sunday at 02:30 local server time.
# Override with:  HOUR=04 WEEKDAY=0 bash scripts/install_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT/scripts/run_weekly_update.sh"
HOUR="${HOUR:-2}"
MINUTE="${MINUTE:-30}"
WEEKDAY="${WEEKDAY:-0}"        # 0 = Sunday
MARK="# latakia-monitor-weekly"
ENTRY="$MINUTE $HOUR * * $WEEKDAY cd $ROOT && bash $RUNNER >/dev/null 2>&1 $MARK"

if ! command -v crontab >/dev/null 2>&1; then
    echo "ERROR: 'crontab' is not available on this system."
    echo "  Ubuntu/Debian:  apt-get install -y cron"
    echo "  CentOS/RHEL:    yum install -y cronie"
    echo "  Windows: use Task Scheduler with scripts/run_weekly_update.sh (Git Bash)."
    exit 1
fi

if [ "${1:-}" = "--remove" ]; then
    crontab -l 2>/dev/null | grep -vF "$MARK" | crontab - || true
    echo "removed: crontab lines matching $MARK"
    exit 0
fi

chmod +x "$RUNNER"
# keep any existing crontab, drop a previously installed line (idempotent)
( crontab -l 2>/dev/null | grep -vF "$MARK"; echo "$ENTRY" ) | crontab -
echo "installed weekly cron (every $([ "$WEEKDAY" = 0 ] && echo Sunday || echo day-of-week $WEEKDAY) at ${HOUR}:${MINUTE}):"
crontab -l | grep -F "$MARK" || true
echo
echo "logs: $ROOT/logs/update_weekly.log"
echo "test run:  bash $RUNNER"
