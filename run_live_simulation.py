#!/usr/bin/env python3
"""
Live Paper Trading Simulation Runner

Connects Oracle signals → Paper Trading Engine → Realtime US market data

Usage:
    export DATABASE_URL="postgresql://..."
    export ORACLE_DATABASE_URL="postgresql://..."
    export ALPHAVANTAGE_API_KEY="..."
    
    python run_live_simulation.py [--cycles N] [--interval SECONDS]
"""
import os
import sys
import time
import logging
import argparse
from decimal import Decimal
from uuid import uuid4

# Add lib to path
sys.path.insert(0, os.path.dirname(__file__))

# Register UUID adapter
import psycopg2.extensions
psycopg2.extensions.register_adapter(type(uuid4()), lambda val: psycopg2.extensions.AsIs(f"'{val}'"))

from lib.engine import PaperTradingEngine
from lib.market_data import AlphaVantageProvider
from lib.strategy_runner import StrategyRunner, RiskRules
from lib.market_session import MarketSession

# Environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')
ORACLE_DATABASE_URL = os.environ.get('ORACLE_DATABASE_URL', DATABASE_URL)
ALPHAVANTAGE_API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

if not ALPHAVANTAGE_API_KEY:
    print("ERROR: ALPHAVANTAGE_API_KEY not set")
    sys.exit(1)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_wallet():
    """Create a test wallet for simulation"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    wallet_id = uuid4()
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            # Check if test wallet already exists
            cur.execute("""
                SELECT id FROM wallets
                WHERE name = 'LiveSim-Test-10K'
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            existing = cur.fetchone()
            if existing:
                logger.info(f"✅ Using existing test wallet: {existing['id']}")
                return existing['id']
            
            # Create new wallet
            cur.execute("""
                INSERT INTO wallets (
                    id, name, capital_tier, initial_balance, current_balance
                ) VALUES (
                    %s, %s, %s, %s, %s
                )
                RETURNING id
            """, (wallet_id, 'LiveSim-Test-10K', '10k', 10000.00, 10000.00))
            
            conn.commit()
            logger.info(f"✅ Created test wallet: {wallet_id}")
            return wallet_id
    finally:
        conn.close()


def print_wallet_summary(engine, wallet_id):
    """Print wallet status"""
    wallet = engine.get_wallet(wallet_id)
    if not wallet:
        return
    
    equity = engine.get_wallet_equity(wallet_id)
    pnl = equity - wallet.initial_balance
    pnl_pct = (pnl / wallet.initial_balance) * 100
    
    positions = engine.get_open_positions(wallet_id)
    
    print("\n" + "="*70)
    print(f"WALLET: {wallet.name}")
    print("="*70)
    print(f"Balance: ${wallet.current_balance:,.2f}")
    print(f"Buying Power: ${wallet.buying_power:,.2f}")
    print(f"Equity: ${equity:,.2f}")
    print(f"PnL: ${pnl:,.2f} ({pnl_pct:+.2f}%)")
    print(f"Open Positions: {len(positions)}")
    
    if positions:
        print("\nPOSITIONS:")
        for pos in positions:
            quote = engine.market_data.get_quote(pos.ticker, pos.market)
            if quote:
                current_value = Decimal(pos.quantity) * quote.price
                unrealised_pnl = current_value - pos.total_cost
                unrealised_pnl_pct = (unrealised_pnl / pos.total_cost) * 100 if pos.total_cost else 0
                print(f"  {pos.ticker}: {pos.quantity} shares @ ${pos.avg_entry_price:.2f} "
                      f"→ ${quote.price:.2f} ({unrealised_pnl_pct:+.2f}%)")


def print_recent_trades(wallet_id):
    """Print recent trades"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM trades
                WHERE wallet_id = %s
                ORDER BY filled_at DESC
                LIMIT 10
            """, (wallet_id,))
            
            trades = cur.fetchall()
            
            if trades:
                print("\nRECENT TRADES:")
                for t in trades:
                    print(f"  {t['filled_at'].strftime('%H:%M:%S')} - "
                          f"{t['side']} {t['quantity']} {t['ticker']} @ ${t['fill_price']:.4f} "
                          f"(slip: {t['slippage_bps']:.1f} bps)")
    finally:
        conn.close()


def print_oracle_diagnostics(runner):
    """Diagnostic: Check Oracle signal freshness"""
    print("\n🔍 ORACLE SIGNAL DIAGNOSTICS")
    print("="*70)
    
    signals = runner.get_oracle_signals(market='US')
    
    if not signals:
        print("❌ NO SIGNALS FOUND")
        print("\nPossible causes:")
        print("  - Oracle database empty")
        print("  - No signals with score >= threshold")
        print("  - Signals older than 24 hours")
        print("\nExiting: Cannot trade without signals")
        return False
    
    print(f"✅ Found {len(signals)} signals\n")
    print("Top 5 Signals:")
    for i, sig in enumerate(signals[:5], 1):
        print(f"  {i}. {sig['ticker']}: score={sig['score']:.2f}, price=${sig['price']:.2f}")
    
    return True


def print_cache_diagnostics(market_data):
    """Diagnostic: Cache health check"""
    if not hasattr(market_data, 'cache') or not market_data.cache:
        print("\n📦 Cache: Empty")
        return
    
    print("\n📦 CACHE STATUS")
    print(f"   Cached tickers: {len(market_data.cache)}")
    
    now = time.time()
    for key, cached in list(market_data.cache.items())[:5]:
        age = now - cached['fetched_at']
        print(f"   {key}: {age:.1f}s old")


def print_rate_limit_status(market_data):
    """Diagnostic: Rate limit telemetry"""
    if not hasattr(market_data, 'requests_this_minute'):
        return
    
    print(f"\n📊 API USAGE")
    print(f"   Requests this minute: {market_data.requests_this_minute}/150")
    
    if market_data.requests_this_minute >= 140:
        print("   ⚠️  WARNING: Approaching rate limit!")


def main():
    parser = argparse.ArgumentParser(description='Live Paper Trading Simulation')
    parser.add_argument('--cycles', type=int, default=5, help='Number of execution cycles')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between cycles')
    parser.add_argument('--min-score', type=int, default=70, help='Minimum Oracle signal score')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be submitted without executing')
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("LIVE PAPER TRADING SIMULATION")
    print("="*70)
    
    # Check market status
    status = MarketSession.get_market_status('US')
    print(f"\n📊 Market Status:")
    print(f"   Market: {status['market']}")
    print(f"   Status: {'🟢 OPEN' if status['is_open'] else '🔴 CLOSED'}")
    print(f"   Local Time: {status['local_time']}")
    if status['next_open']:
        print(f"   Next Open: {status['next_open']}")
    
    if not status['is_open']:
        print("\n⚠️  WARNING: Market is currently CLOSED")
        print("Simulation will run but orders may not execute realistically")
        print()
    
    # Initialize market data provider (realtime)
    print("\n🌐 Initializing market data provider...")
    market_data = AlphaVantageProvider(
        api_key=ALPHAVANTAGE_API_KEY,
        cache_ttl=60,
        use_spread_model=True,
        spread_bps=Decimal('10'),
        require_realtime=True
    )
    print("✅ AlphaVantage Premium (realtime enabled)")
    
    # Initialize paper trading engine
    print("\n⚙️  Initializing paper trading engine...")
    engine = PaperTradingEngine(
        database_url=DATABASE_URL,
        market_data_provider=market_data,
        commission_per_trade=Decimal('1.00'),
        enable_slippage=True
    )
    print("✅ Engine ready")
    
    # Initialize strategy runner
    print("\n📈 Initializing strategy runner...")
    runner = StrategyRunner(
        engine=engine,
        oracle_db_url=ORACLE_DATABASE_URL,
        min_signal_score=args.min_score,
        max_signals=5,
        position_sizing='equal_weight'
    )
    print(f"✅ Strategy ready (min_score: {args.min_score})")
    
    # PRE-LIVE DIAGNOSTIC: Check Oracle signals
    if not print_oracle_diagnostics(runner):
        sys.exit(1)
    
    # DRY RUN mode notification
    if args.dry_run:
        print("\n🔬 DRY RUN MODE ENABLED")
        print("   Orders will be computed but NOT submitted")
        print("="*70)
    
    # Create test wallet
    print("\n💼 Setting up test wallet...")
    wallet_id = create_test_wallet()
    
    # Initial status
    print_wallet_summary(engine, wallet_id)
    
    # Execution loop
    print(f"\n🔄 Starting execution loop ({args.cycles} cycles, {args.interval}s interval)")
    print("="*70)
    
    for cycle in range(1, args.cycles + 1):
        print(f"\n\n{'='*70}")
        print(f"CYCLE {cycle}/{args.cycles}")
        print(f"{'='*70}")
        
        # Diagnostics: Cache health
        print_cache_diagnostics(market_data)
        
        # Diagnostics: Rate limit status
        print_rate_limit_status(market_data)
        
        # Check circuit breaker
        if hasattr(market_data, 'circuit_open') and market_data.circuit_open:
            print("\n🚨 CIRCUIT BREAKER OPEN - Market data provider unavailable")
            print(f"   Consecutive failures: {market_data.consecutive_failures}")
            print("   Skipping cycle")
            continue
        
        # DRY RUN: Show what would be submitted
        if args.dry_run:
            print("\n🔬 DRY RUN: Computing orders (not submitting)...")
            
            wallet = engine.get_wallet(wallet_id)
            signals = runner.get_oracle_signals(market='US')
            current_positions = engine.get_open_positions(wallet_id)
            position_tickers = {p.ticker for p in current_positions}
            
            print(f"\n📋 WOULD SUBMIT:")
            for sig in signals:
                if sig['ticker'] in position_tickers:
                    print(f"   ⏭️  SKIP {sig['ticker']}: Already have position")
                    continue
                
                shares = runner.calculate_position_size(wallet, sig, len(signals))
                estimated_cost = Decimal(shares) * Decimal(str(sig['price']))
                
                is_valid, reason = RiskRules.validate_order(
                    wallet=wallet,
                    ticker=sig['ticker'],
                    estimated_cost=estimated_cost,
                    current_positions=len(current_positions)
                )
                
                if is_valid:
                    print(f"   ✅ BUY {shares} {sig['ticker']} @ ${sig['price']:.2f} = ${estimated_cost:.2f} (score: {sig['score']:.1f})")
                else:
                    print(f"   ❌ REJECT {sig['ticker']}: {reason}")
            
            print("\n🔬 DRY RUN: No orders submitted")
            
        else:
            # LIVE: Execute strategy
            result = runner.execute_strategy_for_wallet(wallet_id)
            
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"\n📊 Execution Results:")
                print(f"   Signals Processed: {result['signals_processed']}")
                print(f"   Orders Submitted: {result['orders_submitted']}")
                print(f"   Orders Rejected: {result['orders_rejected']}")
                
                if result['rejections']:
                    print(f"\n⚠️  Rejections:")
                    for rej in result['rejections']:
                        print(f"      {rej['ticker']}: {rej['reason']}")
            
            # Snapshot metrics (only in live mode)
            runner.snapshot_metrics(wallet_id)
        
        # Show current state
        print_wallet_summary(engine, wallet_id)
        if not args.dry_run:
            print_recent_trades(wallet_id)
        
        # Wait for next cycle
        if cycle < args.cycles:
            print(f"\n⏳ Waiting {args.interval}s until next cycle...")
            time.sleep(args.interval)
    
    # Final summary
    print("\n\n" + "="*70)
    print("SIMULATION COMPLETE")
    print("="*70)
    
    print_wallet_summary(engine, wallet_id)
    print_recent_trades(wallet_id)
    
    print("\n✅ Simulation finished successfully")
    print("\nNext steps:")
    print("  - Review trade ledger in database")
    print("  - Check strategy_metrics table for daily snapshots")
    print("  - Increase wallet count for statistical validation")
    print("  - Build UI dashboard to visualize results")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Simulation interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Simulation failed: {e}", exc_info=True)
        sys.exit(1)
