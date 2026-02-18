"""
Strategy Runner - Connect Oracle signals to Paper Trading Engine
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from .engine import PaperTradingEngine
from .types import OrderIntent, OrderSide, OrderType, Market, Wallet
from .market_session import is_market_open

logger = logging.getLogger(__name__)


class RiskRules:
    """
    Trading risk constraints
    """
    MAX_POSITION_PCT = Decimal('0.20')  # Max 20% per position
    MAX_CONCURRENT_POSITIONS = 5
    MIN_BUYING_POWER_PCT = Decimal('0.10')  # Keep 10% cash reserve
    
    @classmethod
    def validate_order(
        cls,
        wallet: Wallet,
        ticker: str,
        estimated_cost: Decimal,
        current_positions: int
    ) -> tuple[bool, Optional[str]]:
        """
        Validate order against risk rules
        
        Returns: (is_valid, rejection_reason)
        """
        # Check concurrent positions limit
        if current_positions >= cls.MAX_CONCURRENT_POSITIONS:
            return False, f"MAX_POSITIONS_REACHED ({current_positions}/{cls.MAX_CONCURRENT_POSITIONS})"
        
        # Check position size limit
        max_position_size = wallet.initial_balance * cls.MAX_POSITION_PCT
        if estimated_cost > max_position_size:
            return False, f"POSITION_TOO_LARGE (${estimated_cost:.2f} > ${max_position_size:.2f})"
        
        # Check buying power
        min_buying_power = wallet.initial_balance * cls.MIN_BUYING_POWER_PCT
        if wallet.buying_power - estimated_cost < min_buying_power:
            return False, f"INSUFFICIENT_BUYING_POWER (need reserve: ${min_buying_power:.2f})"
        
        return True, None


class StrategyRunner:
    """
    Strategy execution engine
    
    Responsibilities:
    1. Query Oracle signals
    2. Apply risk rules
    3. Generate order intents
    4. Submit to paper trading engine
    5. Snapshot metrics
    """
    
    def __init__(
        self,
        engine: PaperTradingEngine,
        oracle_db_url: str,
        min_signal_score: int = 70,
        max_signals: int = 5,
        position_sizing: str = 'equal_weight'  # or 'percent_buying_power'
    ):
        self.engine = engine
        self.oracle_db_url = oracle_db_url
        self.min_signal_score = min_signal_score
        self.max_signals = max_signals
        self.position_sizing = position_sizing
        self.no_signal_cycles = 0  # Track consecutive cycles with no signals
        self.last_signal_check_time = None  # Track last time we checked for signals
    
    def get_oracle_signals(self, market: str = 'US') -> List[dict]:
        """
        Query Oracle database for top signals
        
        Returns: List of signal dicts with ticker, score, price, etc.
        """
        conn = psycopg2.connect(self.oracle_db_url, cursor_factory=RealDictCursor)
        try:
            with conn.cursor() as cur:
                # Query top signals from last 24 hours
                cur.execute("""
                    SELECT 
                        ticker,
                        score,
                        price,
                        regime,
                        confidence,
                        market
                    FROM instruments
                    WHERE market = %s
                      AND score >= %s
                      AND timestamp > NOW() - INTERVAL '24 hours'
                    ORDER BY score DESC
                    LIMIT %s
                """, (market, self.min_signal_score, self.max_signals))
                
                signals = cur.fetchall()
                logger.info(f"📊 Oracle signals: {len(signals)} found (market: {market}, min_score: {self.min_signal_score})")
                return [dict(s) for s in signals]
        finally:
            conn.close()
    
    def calculate_position_size(
        self,
        wallet: Wallet,
        signal: dict,
        num_signals: int
    ) -> int:
        """
        Calculate position size (number of shares)
        
        Args:
            wallet: Wallet instance
            signal: Oracle signal dict
            num_signals: Total number of signals to distribute capital across
        
        Returns: Number of shares to buy
        """
        if self.position_sizing == 'equal_weight':
            # Divide buying power equally across all signals
            allocation = wallet.buying_power / Decimal(num_signals)
        else:
            # Use percentage of buying power
            allocation = wallet.buying_power * Decimal('0.20')  # 20% per position
        
        # Calculate shares
        price = Decimal(str(signal['price']))
        shares = int(allocation / price)
        
        return max(shares, 1)  # At least 1 share
    
    def execute_strategy_for_wallet(self, wallet_id: UUID) -> Dict:
        """
        Execute strategy for a single wallet
        
        Returns:
            {
                'wallet_id': UUID,
                'signals_processed': int,
                'orders_submitted': int,
                'orders_rejected': int,
                'rejections': List[dict]
            }
        """
        logger.info(f"🎯 Executing strategy for wallet: {wallet_id}")
        
        # Load wallet
        wallet = self.engine.get_wallet(wallet_id)
        if not wallet:
            logger.error(f"Wallet not found: {wallet_id}")
            return {'error': 'WALLET_NOT_FOUND'}
        
        # LIVE SESSION GUARD: Do not execute if market is closed
        if not is_market_open('US'):
            logger.warning("⚠️ MARKET CLOSED - Simulation paused")
            return {
                'error': 'MARKET_CLOSED',
                'message': 'Simulation paused — market closed.',
                'wallet_id': wallet_id,
                'signals_processed': 0,
                'orders_submitted': 0,
                'orders_rejected': 0,
                'rejections': []
            }
        
        # Get current positions
        current_positions = self.engine.get_open_positions(wallet_id)
        position_tickers = {p.ticker for p in current_positions}
        
        # Get Oracle signals
        signals = self.get_oracle_signals(market='US')
        
        if not signals:
            # Only increment cycle counter once per minute (avoid counting all wallets)
            current_time = datetime.now()
            if self.last_signal_check_time is None or (current_time - self.last_signal_check_time).total_seconds() >= 60:
                self.no_signal_cycles += 1
                self.last_signal_check_time = current_time
                logger.warning(f"No signals found (cycle {self.no_signal_cycles})")
            else:
                logger.warning(f"No signals found (cycle {self.no_signal_cycles}, already counted)")
            
            # FALLBACK: Place daily trade when Oracle signals unavailable
            from .fallback_strategy import FallbackStrategy
            
            if FallbackStrategy.should_activate_fallback(self.no_signal_cycles):
                # Check if wallet already traded today
                conn_check = psycopg2.connect(self.oracle_db_url)
                try:
                    should_trade = FallbackStrategy.should_trade_today(str(wallet_id), conn_check)
                finally:
                    conn_check.close()
                
                if not should_trade:
                    logger.info(f"⏭️  {wallet.name}: Already traded today (FALLBACK skipped)")
                    return {
                        'error': 'ALREADY_TRADED_TODAY',
                        'wallet_id': wallet_id,
                        'signals_processed': 0,
                        'orders_submitted': 0,
                        'orders_rejected': 0
                    }
                
                logger.info(f"🔄 FALLBACK ACTIVATED for {wallet.name} - Placing daily trade")
                
                # Generate wallet-specific fallback signal
                fallback_signal = FallbackStrategy.generate_daily_signal(
                    wallet_name=wallet.name,
                    existing_tickers=position_tickers
                )
                
                # Place fallback order
                intent = OrderIntent(
                    wallet_id=wallet_id,
                    ticker=fallback_signal['ticker'],
                    side=OrderSide.BUY,
                    quantity=fallback_signal['quantity'],
                    order_type=OrderType.MARKET,
                    market=Market[fallback_signal['market']]
                )
                
                # Engine returns (order, rejection) tuple
                order, rejection = self.engine.submit_order(intent)
                
                if order and not rejection:
                    logger.info(f"✅ FALLBACK ORDER PLACED: {wallet.name} → {fallback_signal['ticker']} x{fallback_signal['quantity']} (Order ID: {order.id})")
                    
                    # Journal the attempt
                    self._journal_proof_of_life(
                        wallet_id=wallet_id,
                        ticker=fallback_signal['ticker'],
                        quantity=fallback_signal['quantity'],
                        order_id=order.id,
                        status='SUBMITTED',
                        reason=fallback_signal['reason']
                    )
                    
                    return {
                        'wallet_id': wallet_id,
                        'fallback_daily': True,
                        'order_id': str(order.id),
                        'ticker': fallback_signal['ticker'],
                        'quantity': fallback_signal['quantity'],
                        'orders_submitted': 1,
                        'orders_rejected': 0
                    }
                else:
                    logger.error(f"❌ FALLBACK ORDER FAILED for {wallet.name}: {rejection}")
                    
                    # Journal the failure
                    self._journal_proof_of_life(
                        wallet_id=wallet_id,
                        ticker=fallback_signal['ticker'],
                        quantity=fallback_signal['quantity'],
                        order_id=None,
                        status='FAILED',
                        reason=f"FALLBACK_FAILED: {rejection}"
                    )
                    
                    return {
                        'error': 'FALLBACK_ORDER_FAILED',
                        'details': rejection,
                        'wallet_id': wallet_id,
                        'orders_submitted': 0,
                        'orders_rejected': 1
                    }
            
            return {'error': 'NO_SIGNALS'}
        else:
            # Reset counter and timer when signals found
            self.no_signal_cycles = 0
            self.last_signal_check_time = None
        
        # Execute orders
        orders_submitted = 0
        orders_rejected = 0
        rejections = []
        
        for signal in signals:
            ticker = signal['ticker']
            
            # Skip if already have position
            if ticker in position_tickers:
                logger.info(f"⏭️  Skipping {ticker} (already have position)")
                rejections.append({
                    'ticker': ticker,
                    'reason': 'DUPLICATE_POSITION'
                })
                orders_rejected += 1
                continue
            
            # Calculate position size
            shares = self.calculate_position_size(wallet, signal, len(signals))
            estimated_cost = Decimal(shares) * Decimal(str(signal['price']))
            
            # Validate against risk rules
            is_valid, rejection_reason = RiskRules.validate_order(
                wallet=wallet,
                ticker=ticker,
                estimated_cost=estimated_cost,
                current_positions=len(current_positions)
            )
            
            if not is_valid:
                logger.warning(f"❌ Order rejected: {ticker} - {rejection_reason}")
                rejections.append({
                    'ticker': ticker,
                    'reason': rejection_reason
                })
                orders_rejected += 1
                continue
            
            # Create order intent
            intent = OrderIntent(
                wallet_id=wallet_id,
                ticker=ticker,
                market=Market.NASDAQ if signal['market'] == 'US' else Market[signal['market']],
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=shares,
                oracle_signal={
                    'score': float(signal['score']),
                    'regime': signal['regime'],
                    'confidence': float(signal['confidence']) if signal['confidence'] else None,
                    'signal_price': float(signal['price'])
                }
            )
            
            # Submit order
            logger.info(f"📝 Submitting: BUY {shares} {ticker} @ MARKET (score: {signal['score']})")
            order, rejection = self.engine.submit_order(intent)
            
            if rejection:
                logger.error(f"❌ Order rejected: {ticker} - {rejection}")
                rejections.append({
                    'ticker': ticker,
                    'reason': rejection
                })
                orders_rejected += 1
            else:
                logger.info(f"✅ Order submitted: {order.id} ({order.status})")
                orders_submitted += 1
                
                # Update position list
                current_positions = self.engine.get_open_positions(wallet_id)
        
        return {
            'wallet_id': wallet_id,
            'signals_processed': len(signals),
            'orders_submitted': orders_submitted,
            'orders_rejected': orders_rejected,
            'rejections': rejections
        }
    
    def snapshot_metrics(self, wallet_id: UUID) -> None:
        """
        Snapshot wallet metrics to strategy_metrics table
        """
        wallet = self.engine.get_wallet(wallet_id)
        if not wallet:
            return
        
        # Calculate equity
        equity = self.engine.get_wallet_equity(wallet_id)
        
        # Get positions
        positions = self.engine.get_open_positions(wallet_id)
        
        # Calculate unrealised PnL
        unrealised_pnl = Decimal('0')
        for pos in positions:
            quote = self.engine.market_data.get_quote(pos.ticker, pos.market)
            if quote:
                unrealised_pnl += pos.unrealised_pnl(quote.price)
        
        # Calculate realised PnL (from closed positions)
        conn = psycopg2.connect(self.engine.database_url, cursor_factory=RealDictCursor)
        try:
            with conn.cursor() as cur:
                # Get total realised PnL
                cur.execute("""
                    SELECT COALESCE(SUM(realised_pnl), 0) as total_realised
                    FROM positions
                    WHERE wallet_id = %s
                """, (wallet_id,))
                
                result = cur.fetchone()
                realised_pnl = result['total_realised']
                
                # Calculate win rate (from closed positions)
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        COUNT(CASE WHEN realised_pnl > 0 THEN 1 END) as winning_trades
                    FROM positions
                    WHERE wallet_id = %s AND closed_at IS NOT NULL
                """, (wallet_id,))
                
                result = cur.fetchone()
                total_trades = result['total_trades']
                winning_trades = result['winning_trades']
                
                win_rate = Decimal(winning_trades) / Decimal(total_trades) if total_trades > 0 else None
                
                # Calculate exposure
                total_position_value = equity - wallet.current_balance
                exposure_pct = (total_position_value / wallet.initial_balance) if wallet.initial_balance else Decimal('0')
                
                # Insert metrics snapshot
                today = datetime.utcnow().date()
                
                # Upsert (update if exists, insert if not)
                cur.execute("""
                    INSERT INTO strategy_metrics (
                        wallet_id, date, equity, pnl, pnl_pct,
                        win_rate, trade_count, winning_trades, losing_trades
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (wallet_id, date) DO UPDATE SET
                        equity = EXCLUDED.equity,
                        pnl = EXCLUDED.pnl,
                        pnl_pct = EXCLUDED.pnl_pct,
                        win_rate = EXCLUDED.win_rate,
                        trade_count = EXCLUDED.trade_count,
                        winning_trades = EXCLUDED.winning_trades,
                        losing_trades = EXCLUDED.losing_trades,
                        created_at = NOW()
                """, (
                    wallet_id,
                    today,
                    equity,
                    equity - wallet.initial_balance,
                    ((equity - wallet.initial_balance) / wallet.initial_balance) * 100,
                    win_rate,
                    total_trades,
                    winning_trades,
                    total_trades - winning_trades
                ))
                
                conn.commit()
                
                logger.info(f"📊 Metrics snapshot: equity=${equity:.2f}, pnl=${equity - wallet.initial_balance:.2f}")
                
        finally:
            conn.close()
    
    def _ensure_trade_journal_table(self) -> None:
        """Ensure trade_journal table exists"""
        conn = psycopg2.connect(self.engine.database_url)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trade_journal (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
                        ticker TEXT NOT NULL,
                        action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
                        quantity INTEGER NOT NULL,
                        order_id UUID,
                        status TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        outcome TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trade_journal_wallet ON trade_journal(wallet_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trade_journal_created ON trade_journal(created_at DESC)
                """)
                conn.commit()
        finally:
            conn.close()
    
    def _journal_proof_of_life(
        self,
        wallet_id: UUID,
        ticker: str,
        quantity: int,
        order_id: Optional[UUID],
        status: str,
        reason: str
    ) -> None:
        """
        Journal proof-of-life trade attempt (Minimal Viable Journal)
        
        Args:
            wallet_id: Wallet UUID
            ticker: Stock ticker
            quantity: Shares
            order_id: Order ID (if submitted)
            status: SUBMITTED | FAILED
            reason: Why this trade was placed
        """
        # Ensure table exists
        self._ensure_trade_journal_table()
        
        import json
        
        conn = psycopg2.connect(self.engine.database_url)
        try:
            with conn.cursor() as cur:
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
                        %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    wallet_id,
                    'US',
                    ticker,
                    'BUY',
                    'FALLBACK',
                    json.dumps({'quantity': quantity}),
                    [reason],
                    json.dumps({'quantity': quantity, 'order_type': 'MARKET'}),
                    json.dumps({'order_id': str(order_id) if order_id else None, 'status': status}),
                    json.dumps({}),
                    None if order_id else f"FAILED: {status}"
                ))
                conn.commit()
                logger.info(f"📝 Journaled fallback: {ticker} x{quantity} ({status})")
        except Exception as e:
            logger.error(f"❌ Failed to journal proof-of-life: {e}")
            conn.rollback()
        finally:
            conn.close()
