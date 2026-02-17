#!/bin/bash
# Detached Paper Trading Runner - Runs independently of UI
# Critical for overnight trading

set -e

cd "$(dirname "$0")"

# Check environment
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

if [ -z "$ALPHAVANTAGE_API_KEY" ]; then
    echo "ERROR: ALPHAVANTAGE_API_KEY not set"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Activate venv
source ../oracle/venv312/bin/activate

echo "========================================="
echo "PAPER TRADING DETACHED RUNNER"
echo "========================================="
echo ""
echo "This process will:"
echo "  1. Start FastAPI backend (port 8000)"
echo "  2. Run strategy cycles when market is open"
echo "  3. Continue running even if UI is closed"
echo ""
echo "Logs:"
echo "  API: logs/api.log"
echo "  Runner: logs/runner.log"
echo ""
echo "To stop:"
echo "  kill \$(cat logs/runner.pid)"
echo ""
echo "========================================="

# Start API in background
echo "Starting API server..."
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 \
    > logs/api.log 2>&1 &
API_PID=$!
echo $API_PID > logs/api.pid
echo "✓ API started (PID: $API_PID)"

# Wait for API to be ready
sleep 2

# Start strategy runner loop
echo "Starting strategy runner loop..."
python -c '
import os
import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from lib.engine import PaperTradingEngine
from lib.market_data import AlphaVantageProvider
from lib.strategy_runner import StrategyRunner
from lib.market_session import is_market_open
from decimal import Decimal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/runner.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
ALPHAVANTAGE_API_KEY = os.environ["ALPHAVANTAGE_API_KEY"]

# Initialize components
market_data = AlphaVantageProvider(
    api_key=ALPHAVANTAGE_API_KEY,
    cache_ttl=60,
    use_spread_model=True,
    spread_bps=Decimal("10"),
    require_realtime=True
)

engine = PaperTradingEngine(
    database_url=DATABASE_URL,
    market_data_provider=market_data,
    commission_per_trade=Decimal("1.00"),
    enable_slippage=True
)

runner = StrategyRunner(
    engine=engine,
    oracle_db_url=DATABASE_URL,
    min_signal_score=70,
    max_signals=5,
    position_sizing="equal_weight"
)

logger.info("🚀 Detached runner started - will run overnight")
logger.info("📊 Polling every 60s, executing only when market is open")

cycle = 0
while True:
    try:
        cycle += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"Cycle {cycle}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        # Check market status
        if not is_market_open("US"):
            logger.info("⏸️  Market closed - sleeping 60s")
            time.sleep(60)
            continue
        
        # Market is open - execute strategy for all wallets
        logger.info("🟢 Market OPEN - executing strategies")
        
        # Get all wallets
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM wallets")
            wallets = cur.fetchall()
        conn.close()
        
        logger.info(f"📋 Found {len(wallets)} wallets")
        
        # Execute for each wallet
        for wallet in wallets:
            try:
                result = runner.execute_strategy_for_wallet(wallet["id"])
                
                if "error" not in result:
                    logger.info(
                        f"  ✓ {wallet['id'][:8]}: "
                        f"submitted={result['orders_submitted']}, "
                        f"rejected={result['orders_rejected']}"
                    )
                    
                    # Snapshot metrics
                    runner.snapshot_metrics(wallet["id"])
                else:
                    logger.warning(f"  ⚠️  {wallet['id'][:8]}: {result['error']}")
                    
            except Exception as e:
                logger.error(f"  ❌ {wallet['id'][:8]}: {e}")
        
        logger.info(f"✅ Cycle {cycle} complete - sleeping 60s")
        time.sleep(60)
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutdown requested")
        break
    except Exception as e:
        logger.error(f"❌ Cycle error: {e}", exc_info=True)
        time.sleep(60)

logger.info("👋 Detached runner stopped")
' > logs/runner.log 2>&1 &

RUNNER_PID=$!
echo $RUNNER_PID > logs/runner.pid
echo "✓ Runner started (PID: $RUNNER_PID)"

echo ""
echo "========================================="
echo "✅ Detached mode active"
echo "========================================="
echo "  API PID: $API_PID (logs/api.pid)"
echo "  Runner PID: $RUNNER_PID (logs/runner.pid)"
echo ""
echo "Monitor:"
echo "  tail -f logs/api.log"
echo "  tail -f logs/runner.log"
echo ""
echo "Stop:"
echo "  kill \$(cat logs/api.pid)"
echo "  kill \$(cat logs/runner.pid)"
echo "========================================="
