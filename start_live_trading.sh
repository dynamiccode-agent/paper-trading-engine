#!/bin/bash
# Start Live Paper Trading - Automated
# Called by cron at market open

set -e

cd "$(dirname "$0")"

# Load environment
export DATABASE_URL="postgresql://neondb_owner:npg_iMO9K8ogQamB@ep-calm-shape-a7sqncxf-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require"
export ALPHAVANTAGE_API_KEY="99LVCRZIETZ1UUGJ"

# Create logs directory
mkdir -p logs

echo "========================================="
echo "LIVE PAPER TRADING STARTUP"
echo "========================================="
echo "Time: $(date)"
echo "Market: NYSE/NASDAQ"
echo "Wallets: 10 strategy wallets ($100,000 total)"
echo "Note: Filters for strategy wallets (excludes Test-Wallet-*)"
echo "========================================="

# Stop any existing runners
pkill -f "api.main" 2>/dev/null || true
pkill -f "detached.*runner" 2>/dev/null || true
sleep 2

# Start API server
echo "Starting API server..."
nohup /Users/dynamiccode/clawd/quoterite/oracle/venv312/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 \
    > logs/api.log 2>&1 &
API_PID=$!
echo $API_PID > logs/api.pid
echo "✓ API started (PID: $API_PID)"

# Wait for API to be ready
sleep 3

# Start strategy runner (all wallets loop)
echo "Starting strategy runner (10 wallets)..."
nohup /Users/dynamiccode/clawd/quoterite/oracle/venv312/bin/python -u -c "
import os
import sys
import time
import logging
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, '$(pwd)')

from lib.engine import PaperTradingEngine
from lib.market_data import AlphaVantageProvider
from lib.strategy_runner import StrategyRunner
from lib.market_session import is_market_open

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ['DATABASE_URL']
ALPHAVANTAGE_API_KEY = os.environ['ALPHAVANTAGE_API_KEY']

# Initialize components
market_data = AlphaVantageProvider(
    api_key=ALPHAVANTAGE_API_KEY,
    cache_ttl=60,
    use_spread_model=True,
    spread_bps=Decimal('10'),
    require_realtime=True
)

engine = PaperTradingEngine(
    database_url=DATABASE_URL,
    market_data_provider=market_data,
    commission_per_trade=Decimal('1.00'),
    enable_slippage=True
)

runner = StrategyRunner(
    engine=engine,
    oracle_db_url=DATABASE_URL,
    min_signal_score=70,
    max_signals=5,
    position_sizing='equal_weight'
)

logger.info('🚀 Live paper trading started - 10 strategy wallets')
logger.info('📊 60s cycle interval, market-hours only')

cycle = 0
while True:
    try:
        cycle += 1
        logger.info('='*60)
        logger.info(f'Cycle {cycle}: {datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")}')
        logger.info('='*60)
        
        # Market check
        market_open = is_market_open('US')
        logger.info(f'Market status: {\"OPEN\" if market_open else \"CLOSED\"}')
        
        if not market_open:
            logger.info('Market closed - simulation paused')
            time.sleep(60)
            continue
        
        # Get strategy wallets (exclude Test-Wallet-*)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute(\"\"\"
                SELECT id, name FROM wallets 
                WHERE name NOT LIKE 'Test-Wallet-%'
                ORDER BY name
            \"\"\")
            wallets = cur.fetchall()
        conn.close()
        
        logger.info(f'Found {len(wallets)} strategy wallets')
        
        # Execute for each wallet
        for wallet in wallets:
            try:
                result = runner.execute_strategy_for_wallet(wallet['id'])
                
                if 'error' not in result:
                    logger.info(
                        f'  ✓ {wallet[\"name\"]}: '
                        f'submitted={result[\"orders_submitted\"]}, '
                        f'rejected={result[\"orders_rejected\"]}'
                    )
                    runner.snapshot_metrics(wallet['id'])
                else:
                    logger.info(f'  ⚠️  {wallet[\"name\"]}: {result[\"error\"]}')
                    
            except Exception as e:
                logger.error(f'  ❌ {wallet[\"name\"]} error: {e}')
        
        logger.info(f'✅ Cycle {cycle} complete - sleeping 60s')
        time.sleep(60)
        
    except KeyboardInterrupt:
        logger.info('🛑 Shutdown requested')
        break
    except Exception as e:
        logger.error(f'❌ Cycle error: {e}', exc_info=True)
        time.sleep(60)

logger.info('👋 Runner stopped')
" > logs/runner.log 2>&1 &
RUNNER_PID=$!
echo $RUNNER_PID > logs/runner.pid
echo "✓ Runner started (PID: $RUNNER_PID)"

echo ""
echo "========================================="
echo "✅ LIVE TRADING ACTIVE"
echo "========================================="
echo "  API PID: $API_PID"
echo "  Runner PID: $RUNNER_PID"
echo ""
echo "Monitor:"
echo "  tail -f logs/runner.log"
echo "  tail -f logs/api.log"
echo ""
echo "Stop:"
echo "  kill \$(cat logs/runner.pid)"
echo "  kill \$(cat logs/api.pid)"
echo "========================================="

# Log startup to system log
echo "$(date) - Paper trading started (10 wallets, \$100K)" >> logs/startup.log
