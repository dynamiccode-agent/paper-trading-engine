#!/usr/bin/env python3
"""
Simple detached runner test
"""
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
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
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

logger.info("Detached runner test started")
logger.info(f"Market open: {is_market_open('US')}")

# Run 3 cycles
for cycle in range(1, 4):
    logger.info(f"Cycle {cycle}: {datetime.now().strftime('%H:%M:%S')}")
    
    if not is_market_open("US"):
        logger.info("Market closed - paused")
    else:
        logger.info("Market OPEN - executing")
        
        # Get wallets
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM wallets LIMIT 2")
            wallets = cur.fetchall()
        conn.close()
        
        logger.info(f"Testing with {len(wallets)} wallets")
        
        for wallet in wallets:
            try:
                result = runner.execute_strategy_for_wallet(wallet["id"])
                if "error" not in result:
                    logger.info(f"  Wallet {str(wallet['id'])[:8]}: submitted={result['orders_submitted']}")
                else:
                    logger.info(f"  Wallet {str(wallet['id'])[:8]}: {result['error']}")
            except Exception as e:
                logger.error(f"  Wallet error: {e}")
    
    if cycle < 3:
        time.sleep(3)

logger.info("Test complete")
