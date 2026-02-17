#!/bin/bash
# Detached runner - clean test version
set -e

cd "$(dirname "$0")"

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

if [ -z "$ALPHAVANTAGE_API_KEY" ]; then
    echo "ERROR: ALPHAVANTAGE_API_KEY not set"
    exit 1
fi

mkdir -p logs

# Start runner in background
nohup /Users/dynamiccode/clawd/quoterite/oracle/venv312/bin/python -u -c "
import os
import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, '$(pwd)')

from lib.engine import PaperTradingEngine
from lib.market_data import AlphaVantageProvider
from lib.strategy_runner import StrategyRunner
from lib.market_session import is_market_open
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor

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

logger.info('Detached runner started - will cycle every 60s')
logger.info('Market session guard enabled')

cycle = 0
while True:
    try:
        cycle += 1
        logger.info('='*60)
        logger.info(f'Cycle {cycle}: {datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")}')
        logger.info('='*60)
        
        # Check market status
        market_open = is_market_open('US')
        logger.info(f'Market status: {\"OPEN\" if market_open else \"CLOSED\"}')
        
        if not market_open:
            logger.info('Market closed - simulation paused')
            logger.info('Sleeping 60s until next cycle')
            time.sleep(60)
            continue
        
        # Market is open - execute
        logger.info('Market OPEN - executing strategies')
        
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute('SELECT id, name FROM wallets LIMIT 5')
            wallets = cur.fetchall()
        conn.close()
        
        logger.info(f'Found {len(wallets)} wallets')
        
        for wallet in wallets:
            try:
                result = runner.execute_strategy_for_wallet(wallet['id'])
                
                if 'error' not in result:
                    logger.info(
                        f'  Wallet {wallet[\"name\"]}: '
                        f'submitted={result[\"orders_submitted\"]}, '
                        f'rejected={result[\"orders_rejected\"]}'
                    )
                    runner.snapshot_metrics(wallet['id'])
                else:
                    logger.info(f'  Wallet {wallet[\"name\"]}: {result[\"error\"]}')
                    
            except Exception as e:
                logger.error(f'  Wallet {wallet[\"name\"]} error: {e}')
        
        logger.info(f'Cycle {cycle} complete - sleeping 60s')
        time.sleep(60)
        
    except KeyboardInterrupt:
        logger.info('Shutdown requested')
        break
    except Exception as e:
        logger.error(f'Cycle error: {e}', exc_info=True)
        time.sleep(60)

logger.info('Runner stopped')
" > logs/runner.log 2>&1 &

RUNNER_PID=$!
echo $RUNNER_PID > logs/runner.pid

echo "Runner started (PID: $RUNNER_PID)"
echo "Monitor: tail -f logs/runner.log"
echo "Stop: kill \$(cat logs/runner.pid)"
