#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_lock.py — TriSignal Trader V4.3 Lite

Run lock to prevent cron re-entry.

Usage:
    from run_lock import acquire_lock, release_lock

    if not acquire_lock():
        print("Another run is in progress. Exiting.")
        sys.exit(0)
    try:
        # ... main logic ...
    finally:
        release_lock()
"""

import os
import time

LOCK_FILE = "run.lock"
LOCK_TIMEOUT_SECONDS = 3600  # 1 hour — stale lock auto-expire


def acquire_lock() -> bool:
    """
    Try to acquire the run lock.
    Returns True if acquired, False if another run is active.
    Stale locks older than LOCK_TIMEOUT_SECONDS are removed automatically.
    """
    if os.path.exists(LOCK_FILE):
        try:
            mtime = os.path.getmtime(LOCK_FILE)
            age = time.time() - mtime
            if age > LOCK_TIMEOUT_SECONDS:
                os.remove(LOCK_FILE)
                print(f"[run_lock] Removed stale lock (age={int(age)}s)")
            else:
                with open(LOCK_FILE, "r") as f:
                    pid = f.read().strip()
                print(f"[run_lock] Lock held by PID {pid} (age={int(age)}s). Skipping.")
                return False
        except OSError:
            pass

    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except OSError as e:
        print(f"[run_lock] Failed to create lock: {e}")
        return False


def release_lock():
    """Release the run lock."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError as e:
        print(f"[run_lock] Failed to release lock: {e}")
