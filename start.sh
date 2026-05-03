#!/bin/bash

# ── NASDAQ Scanner — start/deploy script ──────────────────────────────────────
# Usage:
#   sudo bash start.sh          → start the scanner in background
#   sudo bash start.sh restart  → kill existing + restart
#   sudo bash start.sh stop     → kill the scanner
#   sudo bash start.sh status   → show if running + last log lines
#   sudo bash start.sh deploy   → git pull + restart

SCANNER_DIR="/home/scanner"
PYTHON="$SCANNER_DIR/venv/bin/python"
SCRIPT="$SCANNER_DIR/live_scanner.py"
LOG="/var/log/scanner.log"
ENV_FILE="$SCANNER_DIR/.env"

# ── Load environment variables ─────────────────────────────────────────────────
set -a
source "$ENV_FILE"
set +a

# ── Helper: is scanner running? ───────────────────────────────────────────────
is_running() {
    pgrep -f "live_scanner.py" > /dev/null 2>&1
}

# ── Commands ──────────────────────────────────────────────────────────────────
case "${1:-start}" in

  start)
    if is_running; then
        echo "Scanner is already running (PID $(pgrep -f live_scanner.py))"
        exit 0
    fi
    echo "Starting scanner..."
    nohup "$PYTHON" "$SCRIPT" >> "$LOG" 2>&1 &
    sleep 2
    if is_running; then
        echo "Scanner started (PID $(pgrep -f live_scanner.py)) — logging to $LOG"
    else
        echo "ERROR: Scanner failed to start. Check $LOG"
        tail -20 "$LOG"
        exit 1
    fi
    ;;

  stop)
    if is_running; then
        pkill -f "live_scanner.py"
        echo "Scanner stopped."
    else
        echo "Scanner is not running."
    fi
    ;;

  restart)
    echo "Restarting scanner..."
    pkill -f "live_scanner.py" 2>/dev/null
    sleep 2
    nohup "$PYTHON" "$SCRIPT" >> "$LOG" 2>&1 &
    sleep 2
    if is_running; then
        echo "Scanner restarted (PID $(pgrep -f live_scanner.py))"
    else
        echo "ERROR: Scanner failed to restart. Check $LOG"
        tail -20 "$LOG"
        exit 1
    fi
    ;;

  status)
    if is_running; then
        echo "Scanner is RUNNING (PID $(pgrep -f live_scanner.py))"
    else
        echo "Scanner is STOPPED"
    fi
    echo ""
    echo "Last 20 log lines:"
    tail -20 "$LOG"
    ;;

  deploy)
    echo "=== Deploying latest from GitHub ==="
    git -C "$SCANNER_DIR" config --global --add safe.directory "$SCANNER_DIR" 2>/dev/null
    git -C "$SCANNER_DIR" pull origin main
    echo ""
    echo "=== Restarting scanner ==="
    pkill -f "live_scanner.py" 2>/dev/null
    sleep 2
    nohup "$PYTHON" "$SCRIPT" >> "$LOG" 2>&1 &
    sleep 2
    if is_running; then
        echo "Scanner deployed and running (PID $(pgrep -f live_scanner.py))"
        echo "Tailing log (Ctrl+C to exit):"
        tail -f "$LOG"
    else
        echo "ERROR: Scanner failed after deploy. Check $LOG"
        tail -20 "$LOG"
        exit 1
    fi
    ;;

  *)
    echo "Usage: sudo bash start.sh [start|stop|restart|status|deploy]"
    exit 1
    ;;

esac
