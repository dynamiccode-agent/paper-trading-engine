"""
Paper Trading Engine - Core execution logic

Order Flow:
1. submit_order(wallet_id, OrderIntent) -> creates Order (status: PENDING)
2. match_and_fill(order_id, Quote) -> creates Trade fills (supports partial fills)
3. apply_fill_to_wallet_and_position() -> updates Wallet + Position atomically
4. Rejection paths return explicit reason codes
"""
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.extensions import register_adapter, AsIs

# Register UUID adapter for psycopg2
register_adapter(UUID, lambda u: AsIs(f"'{u}'::uuid"))

from .types import (
    Order, OrderIntent, Quote, Trade, Position, Wallet,
    OrderStatus, OrderSide, OrderType, Market
)
from .market_data import MarketDataProvider

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """
    Core paper trading execution engine
    
    Responsibilities:
    - Order creation and validation
    - Order matching and fill simulation
    - Wallet and position management
    - Trade ledger (immutable)
    """
    
    def __init__(
        self,
        database_url: str,
        market_data_provider: MarketDataProvider,
        commission_per_trade: Decimal = Decimal('0'),  # Future: configurable commission
        enable_slippage: bool = True
    ):
        self.database_url = database_url
        self.market_data = market_data_provider
        self.commission_per_trade = commission_per_trade
        self.enable_slippage = enable_slippage
    
    def _get_conn(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
    
    # =========================================================================
    # ORDER SUBMISSION
    # =========================================================================
    
    def submit_order(self, intent: OrderIntent) -> tuple[Optional[Order], Optional[str]]:
        """
        Submit order intent → create Order record
        
        Returns: (Order, rejection_reason)
        If rejected: (None, reason)
        If accepted: (Order, None)
        
        Validation:
        1. Wallet exists and has sufficient buying power
        2. Market data available
        3. Order parameters valid
        """
        logger.info(f"📥 Submitting order: {intent.side} {intent.quantity} {intent.ticker}")
        
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # 1. Load wallet
                cur.execute("""
                    SELECT * FROM wallets WHERE id = %s
                """, (intent.wallet_id,))
                wallet_row = cur.fetchone()
                
                if not wallet_row:
                    return None, "WALLET_NOT_FOUND"
                
                wallet = self._row_to_wallet(wallet_row)
                
                # 2. Get current quote
                quote = self.market_data.get_quote(intent.ticker, intent.market)
                if not quote:
                    return None, "NO_MARKET_DATA"
                
                # 2a. Store quote in market_data table for equity calculations
                self._store_market_quote(quote, intent.ticker, intent.market)
                
                # 3. Estimate order cost/proceeds
                if intent.order_type == OrderType.MARKET:
                    # Use ask for BUY, bid for SELL
                    estimated_price = quote.ask if intent.side == OrderSide.BUY else quote.bid
                    if not estimated_price:
                        estimated_price = quote.price
                else:
                    # Use limit price
                    estimated_price = intent.limit_price
                
                estimated_amount = Decimal(intent.quantity) * estimated_price
                
                # 4. Check buying power (BUY only)
                if intent.side == OrderSide.BUY:
                    required = estimated_amount + self.commission_per_trade
                    if not wallet.can_afford(required):
                        return None, f"INSUFFICIENT_FUNDS (need: ${required:.2f}, have: ${wallet.buying_power:.2f})"
                
                # 5. Create order
                order_id = uuid4()
                now = datetime.utcnow()
                
                cur.execute("""
                    INSERT INTO orders (
                        id, wallet_id, ticker, market, side, order_type,
                        quantity, limit_price, stop_price, status, oracle_signal,
                        submitted_at, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    RETURNING *
                """, (
                    order_id, intent.wallet_id, intent.ticker, intent.market.value,
                    intent.side.value, intent.order_type.value,
                    intent.quantity, intent.limit_price, intent.stop_price,
                    OrderStatus.SUBMITTED.value, Json(intent.oracle_signal) if intent.oracle_signal else None,
                    now, now, now
                ))
                
                order_row = cur.fetchone()
                order = self._row_to_order(order_row)
                
                # 6. Reserve buying power (BUY only)
                if intent.side == OrderSide.BUY:
                    cur.execute("""
                        UPDATE wallets
                        SET reserved_balance = reserved_balance + %s,
                            updated_at = %s
                        WHERE id = %s
                    """, (required, now, wallet.id))
                
                conn.commit()
                
                logger.info(f"✅ Order submitted: {order.id} ({order.status})")
                
                # 7. Immediately attempt fill for MARKET orders
                if intent.order_type == OrderType.MARKET:
                    self.match_and_fill(order.id)
                
                return order, None
                
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Order submission failed: {e}", exc_info=True)
            return None, f"SYSTEM_ERROR: {str(e)}"
        finally:
            conn.close()
    
    # =========================================================================
    # ORDER MATCHING & FILLING
    # =========================================================================
    
    def match_and_fill(self, order_id: UUID) -> bool:
        """
        Match and fill order
        
        Returns: True if filled (fully or partially), False otherwise
        
        Fill Logic:
        - MARKET orders: fill at current bid/ask (with slippage)
        - LIMIT orders: fill only if limit price breached
        - Supports partial fills (future: liquidity constraints)
        """
        logger.info(f"🔄 Matching order: {order_id}")
        
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # 1. Load order
                cur.execute("""
                    SELECT * FROM orders WHERE id = %s
                """, (order_id,))
                order_row = cur.fetchone()
                
                if not order_row:
                    logger.error(f"Order not found: {order_id}")
                    return False
                
                order = self._row_to_order(order_row)
                
                if not order.is_active:
                    logger.warning(f"Order not active: {order.status}")
                    return False
                
                # 2. Get current quote
                quote = self.market_data.get_quote(order.ticker, order.market)
                if not quote:
                    logger.warning(f"No market data for {order.ticker}")
                    return False
                
                # 3. Determine fill price
                fill_price = self._calculate_fill_price(order, quote)
                
                if fill_price is None:
                    logger.info(f"Order {order.id} not fillable at current price")
                    return False
                
                # 4. Determine fill quantity (full fill for now, partial fills future)
                fill_quantity = order.remaining_quantity
                
                # 5. Create trade fill
                trade = Trade.from_fill(
                    order_id=order.id,
                    wallet_id=order.wallet_id,
                    ticker=order.ticker,
                    market=order.market,
                    side=order.side,
                    quantity=fill_quantity,
                    fill_price=fill_price,
                    quote=quote,
                    commission=self.commission_per_trade
                )
                
                # 6. Insert trade
                cur.execute("""
                    INSERT INTO trades (
                        id, order_id, wallet_id, ticker, market, side,
                        quantity, fill_price, slippage_bps, commission,
                        gross_amount, net_amount, quote_bid, quote_ask, quote_mid,
                        filled_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s
                    )
                """, (
                    trade.id, trade.order_id, trade.wallet_id, trade.ticker,
                    trade.market.value, trade.side.value,
                    trade.quantity, trade.fill_price, trade.slippage_bps, trade.commission,
                    trade.gross_amount, trade.net_amount, trade.quote_bid, trade.quote_ask,
                    trade.quote_mid, trade.filled_at
                ))
                
                # 7. Update order status
                new_filled_qty = order.filled_quantity + fill_quantity
                if new_filled_qty >= order.quantity:
                    new_status = OrderStatus.FILLED
                else:
                    new_status = OrderStatus.PARTIAL
                
                # Calculate volume-weighted average fill price
                if order.avg_fill_price:
                    total_qty = new_filled_qty
                    avg_fill = (
                        (order.avg_fill_price * order.filled_quantity + fill_price * fill_quantity)
                        / total_qty
                    )
                else:
                    avg_fill = fill_price
                
                now = datetime.utcnow()
                filled_at = now if new_status == OrderStatus.FILLED else None
                
                cur.execute("""
                    UPDATE orders
                    SET filled_quantity = %s,
                        avg_fill_price = %s,
                        status = %s,
                        filled_at = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (new_filled_qty, avg_fill, new_status.value, filled_at, now, order.id))
                
                # 8. Apply fill to wallet and position
                self._apply_fill_to_wallet_and_position(
                    cur, order, trade, fill_quantity
                )
                
                conn.commit()
                
                logger.info(f"✅ Order filled: {fill_quantity} @ ${fill_price} ({new_status})")
                return True
                
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Fill failed: {e}", exc_info=True)
            return False
        finally:
            conn.close()
    
    def _calculate_fill_price(self, order: Order, quote: Quote) -> Optional[Decimal]:
        """
        Calculate fill price based on order type
        
        MARKET: fill at bid (SELL) or ask (BUY), with optional slippage
        LIMIT: fill only if limit breached
        """
        if order.order_type == OrderType.MARKET:
            # Use bid for SELL, ask for BUY
            if order.side == OrderSide.BUY:
                base_price = quote.ask or quote.price
            else:
                base_price = quote.bid or quote.price
            
            # Apply slippage
            if self.enable_slippage and quote.spread:
                # Random slippage within spread (±spread/2)
                slippage_factor = Decimal(random.uniform(-0.5, 0.5))
                slippage = quote.spread * slippage_factor
                fill_price = base_price + slippage
            else:
                fill_price = base_price
            
            # Round to 4 decimals
            return fill_price.quantize(Decimal('0.0001'))
        
        elif order.order_type == OrderType.LIMIT:
            # Fill only if limit breached
            if order.side == OrderSide.BUY:
                # Can fill if ask <= limit
                if quote.ask and quote.ask <= order.limit_price:
                    return quote.ask
            else:
                # Can fill if bid >= limit
                if quote.bid and quote.bid >= order.limit_price:
                    return quote.bid
            
            return None  # Not fillable
        
        # STOP and STOP_LIMIT not yet implemented
        return None
    
    def _apply_fill_to_wallet_and_position(
        self,
        cur,
        order: Order,
        trade: Trade,
        fill_quantity: int
    ) -> None:
        """
        Apply trade fill to wallet balance and position (ATOMIC)
        
        BUY:
        - Deduct net_amount from wallet balance
        - Release reserved balance
        - Increase position quantity + cost basis
        
        SELL:
        - Add net_amount to wallet balance
        - Decrease position quantity
        - Calculate realised PnL
        """
        now = datetime.utcnow()
        
        if order.side == OrderSide.BUY:
            # BUY: deduct from balance, release reserve
            # Load current wallet to get exact reserved amount
            cur.execute("SELECT reserved_balance FROM wallets WHERE id = %s", (order.wallet_id,))
            current_reserved = cur.fetchone()['reserved_balance']
            
            # Release all reserved (avoid negative due to rounding)
            release_amount = min(trade.net_amount, current_reserved)
            
            cur.execute("""
                UPDATE wallets
                SET current_balance = current_balance - %s,
                    reserved_balance = GREATEST(reserved_balance - %s, 0),
                    updated_at = %s
                WHERE id = %s
            """, (trade.net_amount, release_amount, now, order.wallet_id))
            
            # Update/create position
            cur.execute("""
                SELECT * FROM positions
                WHERE wallet_id = %s AND ticker = %s AND market = %s
                  AND closed_at IS NULL
            """, (order.wallet_id, order.ticker, order.market.value))
            
            pos_row = cur.fetchone()
            
            if pos_row:
                # Add to existing position (average up)
                pos = self._row_to_position(pos_row)
                new_qty = pos.quantity + fill_quantity
                new_cost = pos.total_cost + trade.net_amount
                new_avg_entry = new_cost / Decimal(new_qty)
                
                cur.execute("""
                    UPDATE positions
                    SET quantity = %s,
                        avg_entry_price = %s,
                        total_cost = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (new_qty, new_avg_entry, new_cost, now, pos.id))
            else:
                # Create new position
                cur.execute("""
                    INSERT INTO positions (
                        id, wallet_id, ticker, market,
                        quantity, avg_entry_price, total_cost,
                        opened_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                """, (
                    uuid4(), order.wallet_id, order.ticker, order.market.value,
                    fill_quantity, trade.fill_price, trade.net_amount,
                    now, now
                ))
        
        else:  # SELL
            # SELL: add to balance
            cur.execute("""
                UPDATE wallets
                SET current_balance = current_balance + %s,
                    updated_at = %s
                WHERE id = %s
            """, (trade.net_amount, now, order.wallet_id))
            
            # Reduce position
            cur.execute("""
                SELECT * FROM positions
                WHERE wallet_id = %s AND ticker = %s AND market = %s
                  AND closed_at IS NULL
            """, (order.wallet_id, order.ticker, order.market.value))
            
            pos_row = cur.fetchone()
            
            if not pos_row:
                logger.error(f"Position not found for SELL order: {order.ticker}")
                raise ValueError("Cannot SELL without open position")
            
            pos = self._row_to_position(pos_row)
            
            if fill_quantity > pos.quantity:
                logger.error(f"SELL quantity exceeds position: {fill_quantity} > {pos.quantity}")
                raise ValueError("Cannot SELL more than position quantity")
            
            # Calculate realised PnL
            cost_basis_sold = pos.avg_entry_price * Decimal(fill_quantity)
            realised_pnl = trade.gross_amount - cost_basis_sold - trade.commission
            
            new_qty = pos.quantity - fill_quantity
            new_cost = pos.total_cost - cost_basis_sold
            new_realised = pos.realised_pnl + realised_pnl
            
            if new_qty == 0:
                # Close position
                cur.execute("""
                    UPDATE positions
                    SET quantity = 0,
                        total_cost = 0,
                        realised_pnl = %s,
                        closed_at = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (new_realised, now, now, pos.id))
            else:
                # Partial close
                cur.execute("""
                    UPDATE positions
                    SET quantity = %s,
                        total_cost = %s,
                        realised_pnl = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (new_qty, new_cost, new_realised, now, pos.id))
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _row_to_order(self, row: dict) -> Order:
        """Convert DB row to Order"""
        return Order(
            id=row['id'],
            wallet_id=row['wallet_id'],
            ticker=row['ticker'],
            market=Market(row['market']),
            side=OrderSide(row['side']),
            order_type=OrderType(row['order_type']),
            quantity=row['quantity'],
            filled_quantity=row['filled_quantity'],
            limit_price=row['limit_price'],
            stop_price=row['stop_price'],
            avg_fill_price=row['avg_fill_price'],
            status=OrderStatus(row['status']),
            rejection_reason=row['rejection_reason'],
            oracle_signal=row['oracle_signal'],
            submitted_at=row['submitted_at'],
            filled_at=row['filled_at'],
            cancelled_at=row['cancelled_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def _row_to_wallet(self, row: dict) -> Wallet:
        """Convert DB row to Wallet"""
        return Wallet(
            id=row['id'],
            name=row['name'],
            capital_tier=row['capital_tier'],
            initial_balance=row['initial_balance'],
            current_balance=row['current_balance'],
            reserved_balance=row['reserved_balance'],
            strategy_id=row['strategy_id'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def _row_to_position(self, row: dict) -> Position:
        """Convert DB row to Position"""
        return Position(
            id=row['id'],
            wallet_id=row['wallet_id'],
            ticker=row['ticker'],
            market=Market(row['market']),
            quantity=row['quantity'],
            avg_entry_price=row['avg_entry_price'],
            total_cost=row['total_cost'],
            realised_pnl=row['realised_pnl'],
            opened_at=row['opened_at'],
            closed_at=row['closed_at'],
            updated_at=row['updated_at']
        )
    
    def _store_market_quote(self, quote: Quote, ticker: str, market: Market) -> None:
        """Store market quote in market_data table for equity calculations"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market_data (
                        ticker, market, price, bid, ask, volume, timestamp, fetched_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    ON CONFLICT (ticker, market, timestamp) DO UPDATE SET
                        price = EXCLUDED.price,
                        bid = EXCLUDED.bid,
                        ask = EXCLUDED.ask,
                        volume = EXCLUDED.volume,
                        fetched_at = NOW()
                """, (
                    ticker,
                    market.value,
                    quote.price,
                    quote.bid,
                    quote.ask,
                    quote.volume,
                    quote.timestamp
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to store market quote for {ticker}: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    def get_wallet(self, wallet_id: UUID) -> Optional[Wallet]:
        """Get wallet by ID"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM wallets WHERE id = %s", (wallet_id,))
                row = cur.fetchone()
                return self._row_to_wallet(row) if row else None
        finally:
            conn.close()
    
    def get_open_positions(self, wallet_id: UUID) -> List[Position]:
        """Get all open positions for wallet"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM positions
                    WHERE wallet_id = %s AND closed_at IS NULL
                    ORDER BY opened_at DESC
                """, (wallet_id,))
                return [self._row_to_position(row) for row in cur.fetchall()]
        finally:
            conn.close()
    
    def get_wallet_equity(self, wallet_id: UUID) -> Decimal:
        """Calculate wallet equity (balance + position values)"""
        wallet = self.get_wallet(wallet_id)
        if not wallet:
            return Decimal('0')
        
        positions = self.get_open_positions(wallet_id)
        position_value = Decimal('0')
        
        for pos in positions:
            quote = self.market_data.get_quote(pos.ticker, pos.market)
            if quote:
                position_value += Decimal(pos.quantity) * quote.price
        
        return wallet.current_balance + position_value
