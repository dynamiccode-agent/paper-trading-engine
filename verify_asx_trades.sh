#!/bin/bash
# Verify ASX Paper Trading Activity
# Shows last 10 trade_journal entries for ASX tickers

cd "$(dirname "$0")"

echo "========================================="
echo "ASX TRADE VERIFICATION"
echo "========================================="
echo "Time: $(date)"
echo ""

# Check if ASX runner is active
if [ -f logs/runner_asx.pid ]; then
    ASX_PID=$(cat logs/runner_asx.pid)
    if ps -p $ASX_PID > /dev/null 2>&1; then
        echo "✅ ASX Runner: ACTIVE (PID: $ASX_PID)"
    else
        echo "❌ ASX Runner: STOPPED"
    fi
else
    echo "❌ ASX Runner: NOT STARTED"
fi

echo ""
echo "========================================="
echo "LAST 10 ASX TRADE JOURNAL ENTRIES"
echo "========================================="

python3 << 'EOF'
import os
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get last 10 ASX trades (tickers ending in .AX)
    cur.execute("""
        SELECT 
            created_at,
            ticker,
            action,
            quantity,
            limit_price,
            status,
            order_id,
            reason
        FROM trade_journal
        WHERE ticker LIKE '%.AX'
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    trades = cur.fetchall()
    
    if trades:
        for t in trades:
            print(f"{t['created_at']} | {t['action']} {t['quantity']:>4} {t['ticker']:10} @ ${t['limit_price']:>8.2f} | {t['status']:10} | Order: {t['order_id']}")
    else:
        print("No ASX trades found in trade_journal")
    
    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
EOF

echo ""
echo "========================================="
echo "ASX RUNNER LOG (LAST 20 LINES)"
echo "========================================="

if [ -f logs/runner_asx.log ]; then
    tail -20 logs/runner_asx.log | grep -E "(Cycle|FALLBACK|ASX|Market status|proof-of-life)"
else
    echo "No ASX log file found"
fi

echo ""
echo "========================================="
