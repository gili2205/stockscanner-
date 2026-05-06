#!/bin/bash

export ALPACA_KEY=PK55MZO64HVY3LM764ZIVHSMNY
export ALPACA_SECRET=6hZg69XTG1DpVf8M3e2amUdFBDCExRg5zcyKgLaneqoN
export FIREBASE_URL=https://stockscanner-f9f81-default-rtdb.firebaseio.com
export FIREBASE_CRED=/home/scanner/firebase-key.json

VENV=/home/scanner/venv/bin/python

case "$1" in
  start)
    systemctl start scanner
    ;;
  stop)
    systemctl stop scanner
    ;;
  restart)
    systemctl restart scanner
    ;;
  status)
    systemctl status scanner --no-pager -l
    ;;
  deploy)
    echo "Stopping scanner..."
    systemctl stop scanner
    echo "Pulling from GitHub..."
    cd /home/scanner
    git pull origin main
    echo "Restarting scanner..."
    systemctl start scanner
    echo "Done."
    systemctl status scanner --no-pager | tail -5
    ;;
  run-backtest)
    DAYS=${2:-30}
    echo "Starting backtest ($DAYS days) in background..."
    cd /home/scanner
    screen -dmS backtest bash -c "
      export FIREBASE_URL=$FIREBASE_URL
      export FIREBASE_CRED=$FIREBASE_CRED
      $VENV backtest.py --days $DAYS 2>&1 | tee /var/log/backtest.log
    "
    echo "Backtest running. Check: sudo bash start.sh backtest-log"
    ;;
  backtest-log)
    tail -f /var/log/backtest.log
    ;;
  update-returns)
    cd /home/scanner
    export FIREBASE_URL=$FIREBASE_URL
    export FIREBASE_CRED=$FIREBASE_CRED
    $VENV backtest.py --update-returns
    ;;
  logs)
    tail -f /var/log/scanner.log
    ;;
  *)
    echo "Usage: sudo bash start.sh {start|stop|restart|status|deploy|run-backtest [days]|backtest-log|update-returns|logs}"
    ;;
esac
