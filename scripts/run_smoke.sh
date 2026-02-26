#!/usr/bin/env bash
set -euo pipefail

DF_ROOT="${DF_ROOT:-/home/sober/df53/app}"
LOG_DIR="${LOG_DIR:-$DF_ROOT/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/smoke_$(date +%s).log"

if [[ ! -x "$DF_ROOT/tools/smoke.exp" ]]; then
  echo "ERROR: missing $DF_ROOT/tools/smoke.exp"
  exit 1
fi

echo "[smoke] DF_ROOT=$DF_ROOT"
echo "[smoke] LOG_FILE=$LOG_FILE"
"$DF_ROOT/tools/smoke.exp" "$LOG_FILE"

echo "[smoke] done"
echo "[smoke] tail:"
tail -n 40 "$LOG_FILE" || true
