#!/bin/bash
# Paper Trading Monitor Script
# Checks US and ASX runners, reports status

cd "$(dirname "$0")"

echo "========================================="
echo "PAPER TRADING MONITOR"
echo "Time: $(date)"
echo "========================================="

# Check US Runner
US_STATUS="❌ NOT RUNNING"
if [ -f logs/runner.pid ]; then
    US_PID=$(cat logs/runner.pid)
    if ps -p $US_PID > /dev/null 2>&1; then
        US_STATUS="✅ ACTIVE (PID: $US_PID)"
    else
        US_STATUS="❌ CRASHED (PID $US_PID not found)"
    fi
fi

echo "US Runner: $US_STATUS"

# Check ASX Runner
ASX_STATUS="❌ NOT RUNNING"
if [ -f logs/runner_asx.pid ]; then
    ASX_PID=$(cat logs/runner_asx.pid)
    if ps -p $ASX_PID > /dev/null 2>&1; then
        ASX_STATUS="✅ ACTIVE (PID: $ASX_PID)"
    else
        ASX_STATUS="❌ CRASHED (PID $ASX_PID not found)"
    fi
fi

echo "ASX Runner: $ASX_STATUS"

# Check market hours
HOUR=$(date +%H)
MINUTE=$(date +%M)
TIME_NUM=$((10#$HOUR * 60 + 10#$MINUTE))

# US market: 1:30-8:00 AEST (90-480 minutes)
US_MARKET="CLOSED"
if [ $TIME_NUM -ge 90 ] && [ $TIME_NUM -lt 480 ]; then
    US_MARKET="OPEN"
fi

# ASX market: 10:00-16:00 AEST (600-960 minutes)
ASX_MARKET="CLOSED"
if [ $TIME_NUM -ge 600 ] && [ $TIME_NUM -lt 960 ]; then
    ASX_MARKET="OPEN"
fi

echo "US Market: $US_MARKET"
echo "ASX Market: $ASX_MARKET"

# Alert logic
ALERT=""

if [ "$US_MARKET" = "OPEN" ] && [[ "$US_STATUS" == *"NOT RUNNING"* || "$US_STATUS" == *"CRASHED"* ]]; then
    ALERT="⚠️ US market OPEN but runner NOT ACTIVE"
fi

if [ "$ASX_MARKET" = "OPEN" ] && [[ "$ASX_STATUS" == *"NOT RUNNING"* || "$ASX_STATUS" == *"CRASHED"* ]]; then
    ALERT="${ALERT}\n⚠️ ASX market OPEN but runner NOT ACTIVE"
fi

# Check for recent errors
if [ -f logs/runner.log ]; then
    US_ERRORS=$(tail -20 logs/runner.log | grep -i "error\|failed\|exception" | wc -l | tr -d ' ')
    if [ $US_ERRORS -gt 0 ]; then
        ALERT="${ALERT}\n⚠️ US runner has $US_ERRORS recent errors"
    fi
fi

if [ -f logs/runner_asx.log ]; then
    ASX_ERRORS=$(tail -20 logs/runner_asx.log | grep -i "error\|failed\|exception" | wc -l | tr -d ' ')
    if [ $ASX_ERRORS -gt 0 ]; then
        ALERT="${ALERT}\n⚠️ ASX runner has $ASX_ERRORS recent errors"
    fi
fi

echo "========================================="

if [ -n "$ALERT" ]; then
    echo -e "$ALERT"
    exit 1
else
    echo "✅ All systems operational"
    exit 0
fi
