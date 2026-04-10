#!/usr/bin/env bash
# lock.sh — run lock helper for TriSignal Trader
# Usage:
#   source lock.sh acquire   → exits with code 1 if lock held
#   source lock.sh release   → removes lock file

LOCK_FILE="$(dirname "$0")/run.lock"
LOCK_TIMEOUT=3600  # seconds before a lock is considered stale

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_FILE" 2>/dev/null || stat -c %Y "$LOCK_FILE") ))
        if [ "$lock_age" -lt "$LOCK_TIMEOUT" ]; then
            pid=$(cat "$LOCK_FILE" 2>/dev/null)
            echo "[run_lock] Lock held by PID $pid (age=${lock_age}s). Skipping this cycle."
            exit 0
        else
            echo "[run_lock] Removing stale lock (age=${lock_age}s)."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    echo "[run_lock] Lock acquired (PID=$$)."
}

release_lock() {
    rm -f "$LOCK_FILE"
    echo "[run_lock] Lock released."
}

case "$1" in
    acquire) acquire_lock ;;
    release) release_lock ;;
    *) echo "Usage: $0 acquire|release" ;;
esac
