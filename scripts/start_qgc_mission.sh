#!/bin/bash
# Detach the QGC mission runner from the short-lived Windows wsl.exe session.
set -euo pipefail

LOG_DIR=/home/hw/logs
RUNNER=/home/hw/tools/run_qgc_mission.sh
mkdir -p "$LOG_DIR"

setsid -f bash "$RUNNER" > "$LOG_DIR/qgc_mission_launcher.log" 2>&1
for _attempt in 1 2 3 4 5; do
    if pgrep -af 'qgc_mission_runner' >/dev/null; then
        pgrep -af 'qgc_mission_runner'
        exit 0
    fi
    sleep 1
done
echo "qgc_mission_runner failed to stay alive" >&2
cat "$LOG_DIR/qgc_mission_launcher.log" >&2 || true
exit 1
