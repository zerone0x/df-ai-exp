#!/usr/bin/env bash
set -euo pipefail

DF_ROOT="${DF_ROOT:-/home/sober/df53/app}"
LOG_DIR="$DF_ROOT/logs"
mkdir -p "$LOG_DIR"
DAEMON_LOG="$LOG_DIR/daemon_$(date +%s).log"

# Start DFHack host process
nohup xvfb-run -a -s '-screen 0 1280x720x24' "$DF_ROOT/dfhack" > "$DAEMON_LOG" 2>&1 &
PID=$!
trap 'kill $PID >/dev/null 2>&1 || true' EXIT

sleep 8

# Run commands through non-interactive channel
"$DF_ROOT/dfhack-run" ls > "$LOG_DIR/dfhack_run_ls.log" 2>&1 || true
"$DF_ROOT/dfhack-run" help > "$LOG_DIR/dfhack_run_help.log" 2>&1 || true

echo "daemon_pid=$PID"
echo "daemon_log=$DAEMON_LOG"
echo "ls_log=$LOG_DIR/dfhack_run_ls.log"
echo "help_log=$LOG_DIR/dfhack_run_help.log"
