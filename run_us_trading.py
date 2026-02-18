#!/usr/bin/env python3
"""
US Paper Trading Runner - 10 Strategy Wallets
Daily Fallback Mode (1 trade/wallet/day when Oracle unavailable)
"""
import os
import sys
import time
import logging
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, '/Users/dynamiccode/clawd/quoterite/paper_trading')

from lib.engine import PaperTradingEngine
from lib.market_data import AlphaVantageProvider
from lib.strategy_runner import StrategyRunner
from lib.market_session import is_market_open

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/runner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://neondb_owner:npg_iMO9K8ogQamB@ep-calm-shape-a7sqncxf-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require')
ALPHAVANTAGE_API_KEY = os.getenv('ALPHAVANTAGE_API_KEY', '')

# Initialize components
market_data = AlphaVantageProvider(
    api_key=ALPHAVANTAGE_API_KEY,
    cache_ttl=60,
    use_spread_model=True,
    spread_bps=Decimal('10'),
    require_realtime=False  # Use fallback pricing when API unavailable
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

logger.info('🚀 US Paper Trading Runner Started')
logger.info('📊 10 strategy wallets')
logger.info('🔄 Daily fallback mode (1 trade/wallet/day when Oracle unavailable)')
logger.info('⏱️  60s cycle interval, market-hours only')

cycle = 0
while True:
    try:
        cycle += 1
        logger.info('='*60)
        logger.info(f'Cycle {cycle}: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        logger.info('='*60)
        
        # Market check
        market_open = is_market_open('US')
        logger.info(f'Market status: {"OPEN" if market_open else "CLOSED"}')
        
        if not market_open:
            logger.info('Market closed - simulation paused')
            time.sleep(60)
            continue
        
        # Get strategy wallets (exclude Test-Wallet-*)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name FROM wallets 
                WHERE name NOT LIKE 'Test-Wallet-%'
                ORDER BY name
            """)
            wallets = cur.fetchall()
        conn.close()
        
        logger.info(f'Found {len(wallets)} strategy wallets')
        
        # Execute for each wallet
        for wallet in wallets:
            try:
                result = runner.execute_strategy_for_wallet(wallet['id'])
                
                if 'error' not in result:
                    logger.info(
                        f'  ✅ {wallet["name"]}: '
                        f'submitted={result.get("orders_submitted", 0)}, '
                        f'rejected={result.get("orders_rejected", 0)}'
                    )
                    if result.get('fallback_daily'):
                        logger.info(f'     └─ FALLBACK: {result.get("ticker")} x{result.get("quantity")}')
                    runner.snapshot_metrics(wallet['id'])
                elif result.get('error') == 'ALREADY_TRADED_TODAY':
                    logger.info(f'  ⏭️  {wallet["name"]}: Already traded today')
                elif result.get('error') == 'NO_SIGNALS':
                    logger.info(f'  ⚠️  {wallet["name"]}: NO_SIGNALS')
                else:
                    logger.info(f'  ⚠️  {wallet["name"]}: {result.get("error")}')
                    
            except Exception as e:
                logger.error(f'  ❌ {wallet["name"]} error: {e}')
        
        logger.info(f'✅ Cycle {cycle} complete - sleeping 60s')
        time.sleep(60)
        
    except KeyboardInterrupt:
        logger.info('🛑 Shutdown requested')
        break
    except Exception as e:
        logger.error(f'❌ Cycle error: {e}', exc_info=True)
        time.sleep(60)

logger.info('🏁 Runner stopped')
