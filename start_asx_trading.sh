#!/bin/bash
# ASX Paper Trading Startup Script
# Separate from US runner - ASX hours only (10:00-16:00 AEST)

set -e

cd "$(dirname "$0")"

echo "========================================="
echo "ASX PAPER TRADING STARTUP"
echo "========================================="
echo "Time: $(date)"
echo "Market: ASX (10:00-16:00 AEST)"
echo "Mode: PROOF-OF-LIFE (1 wallet, $500 AUD min)"
echo "========================================="

# Check if already running
if [ -f logs/runner_asx.pid ]; then
    OLD_PID=$(cat logs/runner_asx.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "⚠️  ASX runner already running (PID: $OLD_PID)"
        echo "Stop it first: kill \$(cat logs/runner_asx.pid)"
        exit 1
    fi
fi

# Ensure logs directory
mkdir -p logs

# Check required env vars
if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL not set"
    exit 1
fi

if [ -z "$ALPHAVANTAGE_API_KEY" ]; then
    echo "❌ ERROR: ALPHAVANTAGE_API_KEY not set"
    exit 1
fi

echo "Starting ASX runner..."

# Start ASX runner using venv Python
VENV_PYTHON="../oracle/venv312/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

nohup $VENV_PYTHON run_asx_trading.py > logs/runner_asx.log 2>&1 &
ASX_PID=$!
echo $ASX_PID > logs/runner_asx.pid

sleep 2

# Verify process started
if ps -p $ASX_PID > /dev/null; then
    echo "✓ ASX Runner started (PID: $ASX_PID)"
else
    echo "❌ ASX Runner failed to start"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ ASX TRADING ACTIVE"
echo "========================================="
echo "  ASX Runner PID: $ASX_PID"
echo ""
echo "Monitor:"
echo "  tail -f logs/runner_asx.log"
echo ""
echo "Stop:"
echo "  kill \$(cat logs/runner_asx.pid)"
echo "========================================="
