#!/bin/bash

SCANNER_DIR=/home/scanner
VENV=$SCANNER_DIR/venv/bin/python
LOG=/var/log/scanner.log

export ALPACA_KEY=PK55MZO64HVY3LM764ZIVHSMNY
export ALPACA_SECRET=6hZg69XTG1DpVf8M3e2amUdFBDCExRg5zcyKgLaneqoN
export FIREBASE_URL=https://stockscanner-f9f81-default-rtdb.firebaseio.com
export FIREBASE_CRED=$SCANNER_DIR/firebase-key.json

case "$1" in

  start)
    echo "Starting scanner..."
    systemctl start scanner
    ;;

  stop)
    echo "Stopping scanner..."
    systemctl stop scanner
    ;;

  restart)
    echo "Restarting scanner..."
    systemctl restart scanner
    ;;

  status)
    systemctl status scanner --no-pager -l
    ;;

  deploy)
    echo "=== Deploying from GitHub ==="
    systemctl stop scanner

    cd $SCANNER_DIR
    if [ -d ".git" ]; then
      echo "Pulling latest from GitHub..."
      git pull origin main
    else
      echo "Cloning repo..."
      git clone https://github.com/gili2205/stockscanner-.git .
    fi

    echo "Files deployed:"
    ls $SCANNER_DIR/*.py 2>/dev/null

    if [ -f $SCANNER_DIR/requirements.txt ]; then
      echo "Installing requirements..."
      $SCANNER_DIR/venv/bin/pip install -r $SCANNER_DIR/requirements.txt -q
    fi

    echo "Restarting scanner..."
    systemctl start scanner
    echo "=== Deploy complete ==="
    systemctl status scanner --no-pager | tail -3
    ;;

  run-backtest)
    DAYS=${2:-30}
    echo "=== Starting backtest ($DAYS days) in background ==="
    cd $SCANNER_DIR
    screen -dmS backtest bash -c "
      export FIREBASE_URL=$FIREBASE_URL
      export FIREBASE_CRED=$FIREBASE_CRED
      $VENV backtest.py --days $DAYS 2>&1 | tee /var/log/backtest.log
    "
    echo "Backtest running. Check progress: sudo bash start.sh backtest-log"
    ;;

  backtest-log)
    tail -f /var/log/backtest.log
    ;;

  update-returns)
    echo "=== Updating forward returns ==="
    cd $SCANNER_DIR
    export FIREBASE_URL=$FIREBASE_URL
    export FIREBASE_CRED=$FIREBASE_CRED
    $VENV backtest.py --update-returns
    ;;

  logs)
    tail -f $LOG
    ;;

  *)
    echo "Usage: sudo bash start.sh {start|stop|restart|status|deploy|run-backtest [days]|backtest-log|update-returns|logs}"
    ;;

esac
