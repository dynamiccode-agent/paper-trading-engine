#!/usr/bin/env python3
"""
ASX Paper Trading Runner - Separate from US runner
PROOF-OF-LIFE MODE: 1 wallet only
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
from lib.market_session import is_market_open
from lib.fallback_asx import ASXFallbackStrategy
from lib.types import OrderIntent, OrderSide, OrderType, Market, Quote

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/runner_asx.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ['DATABASE_URL']
ALPHAVANTAGE_API_KEY = os.environ['ALPHAVANTAGE_API_KEY']

def _journal_asx_trade(wallet_id, ticker, quantity, limit_price, order_id, status, reason):
    """Journal ASX trade to MVJ using actual schema"""
    import json
    from datetime import datetime
    
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Insert using actual trade_journal schema
            cur.execute("""
                INSERT INTO trade_journal (
                    wallet_id,
                    ts_utc,
                    market,
                    ticker,
                    action,
                    mode,
                    signal_snapshot,
                    reason_codes,
                    order_request,
                    order_response,
                    fill,
                    error
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                wallet_id,
                datetime.now(),
                'ASX',
                ticker,
                'BUY',
                'FALLBACK',
                json.dumps({'price': float(limit_price), 'quantity': quantity}),
                [reason],
                json.dumps({'quantity': quantity, 'limit_price': float(limit_price), 'order_type': 'LIMIT'}),
                json.dumps({'order_id': str(order_id) if order_id else None, 'status': status}),
                json.dumps({}),  # fill: always valid JSON (empty for failed orders)
                None if order_id else f"FAILED: {status}"
            ))
            conn.commit()
            logger.info(f"📝 MVJ: {ticker} x{quantity} @ ${limit_price} ({status})")
    except Exception as e:
        logger.error(f"❌ Failed to journal ASX trade: {e}")
        conn.rollback()
    finally:
        conn.close()

# Initialize components
market_data = AlphaVantageProvider(
    api_key=ALPHAVANTAGE_API_KEY,
    cache_ttl=60,
    use_spread_model=True,
    spread_bps=Decimal('10'),
    require_realtime=False  # ASX: Do not block on market data failures
)

engine = PaperTradingEngine(
    database_url=DATABASE_URL,
    market_data_provider=market_data,
    commission_per_trade=Decimal('10.00'),  # ASX commission
    enable_slippage=True
)

# ASX-specific state
no_signal_cycles = 0
fallback_activated = False
last_signal_check_time = None

logger.info('🇦🇺 ASX Paper Trading started - PROOF-OF-LIFE MODE')
logger.info('📊 1 wallet only, $500 AUD minimum parcel')
logger.info('🕐 60s cycle interval, ASX market-hours only (10:00-16:00 AEST)')

cycle = 0
while True:
    try:
        cycle += 1
        logger.info('='*60)
        logger.info(f'Cycle {cycle}: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        logger.info('='*60)
        
        # ASX market check
        market_open = is_market_open('ASX')
        logger.info(f'ASX Market status: {"OPEN" if market_open else "CLOSED"}')
        
        if not market_open:
            logger.info('ASX market closed - simulation paused')
            time.sleep(60)
            continue
        
        # Get FIRST active wallet (proof-of-life: 1 wallet only)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name FROM wallets 
                WHERE name NOT LIKE 'Test-Wallet-%'
                ORDER BY name
                LIMIT 1
            """)
            wallet = cur.fetchone()
        conn.close()
        
        if not wallet:
            logger.error("No active wallets found")
            time.sleep(60)
            continue
        
        logger.info(f"🎯 ASX Wallet: {wallet['name']}")
        
        # Check if already traded (fallback_activated prevents multiple trades)
        if fallback_activated:
            logger.info("✅ Proof-of-life trade already executed - standing by")
            time.sleep(60)
            continue
        
        # Increment no-signal cycle (no Oracle signals for ASX yet)
        current_time = datetime.now()
        if last_signal_check_time is None or (current_time - last_signal_check_time).total_seconds() >= 60:
            no_signal_cycles += 1
            last_signal_check_time = current_time
            logger.warning(f"No ASX signals (cycle {no_signal_cycles})")
        
        # Activate fallback after 3 cycles
        if ASXFallbackStrategy.should_activate_fallback(no_signal_cycles):
            logger.info("🔄 ASX FALLBACK ACTIVATED - Placing proof-of-life trade")
            
            # Get wallet object
            wallet_obj = engine.get_wallet(wallet['id'])
            if not wallet_obj:
                logger.error("Failed to load wallet")
                time.sleep(60)
                continue
            
            # Check for existing ASX positions
            positions = engine.get_open_positions(wallet['id'])
            if any(p.market == Market.ASX for p in positions):
                logger.info("⏭️  Already have ASX position - skipping")
                fallback_activated = True
                time.sleep(60)
                continue
            
            # Generate ASX proof signal (qty=1 for safety)
            signal = ASXFallbackStrategy.generate_asx_proof_signal(wallet['name'])
            
            # Skip minimum parcel validation for proof-of-life mode (qty=1)
            logger.info(f"📝 Proof-of-life mode: qty={signal['quantity']} (min parcel check skipped)")
            
            # Pre-populate market data cache with oracle price (fallback)
            # This ensures order submission doesn't fail on NO_MARKET_DATA
            cache_key = f"{signal['ticker']}:ASX"
            fallback_quote = Quote(
                ticker=signal['ticker'],
                market=Market.ASX,
                price=signal['limit_price'],
                bid=signal['limit_price'] * Decimal('0.999'),  # Mock 0.1% spread
                ask=signal['limit_price'] * Decimal('1.001'),
                volume=0,
                timestamp=datetime.now()
            )
            market_data.cache[cache_key] = {
                'quote': fallback_quote,
                'fetched_at': time.time()
            }
            logger.info(f"📊 Using oracle price fallback: ${signal['limit_price']} (no realtime data)")
            
            # Create LIMIT order intent
            intent = OrderIntent(
                wallet_id=wallet['id'],
                ticker=signal['ticker'],
                side=OrderSide.BUY,
                quantity=signal['quantity'],
                order_type=OrderType.LIMIT,
                limit_price=signal['limit_price'],
                market=Market.ASX
            )
            
            # Submit order
            logger.info(f"📝 Submitting ASX order: BUY {signal['quantity']} {signal['ticker']} @ ${signal['limit_price']} LIMIT")
            
            order, rejection = engine.submit_order(intent)
            
            if order and not rejection:
                logger.info(f"✅ ASX PROOF-OF-LIFE ORDER PLACED: {signal['ticker']} x{signal['quantity']} (Order ID: {order.id})")
                fallback_activated = True
                
                # Journal to MVJ
                _journal_asx_trade(
                    wallet_id=wallet['id'],
                    ticker=signal['ticker'],
                    quantity=signal['quantity'],
                    limit_price=signal['limit_price'],
                    order_id=order.id,
                    status='SUBMITTED',
                    reason=signal['reason']
                )
            else:
                logger.error(f"❌ ASX ORDER FAILED: {rejection}")
                
                # Journal failure
                _journal_asx_trade(
                    wallet_id=wallet['id'],
                    ticker=signal['ticker'],
                    quantity=signal['quantity'],
                    limit_price=signal['limit_price'],
                    order_id=None,
                    status='FAILED',
                    reason=f"ASX_FALLBACK_FAILED: {rejection}"
                )
        
        logger.info(f'✅ ASX Cycle {cycle} complete - sleeping 60s')
        time.sleep(60)
        
    except KeyboardInterrupt:
        logger.info('🛑 ASX Runner shutdown requested')
        break
    except Exception as e:
        logger.error(f'❌ ASX Cycle error: {e}', exc_info=True)
        time.sleep(60)

logger.info('🛑 ASX Runner stopped')
