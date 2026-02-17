"""
Core types for paper trading engine
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Market(str, Enum):
    ASX = "ASX"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    TSX = "TSX"


@dataclass
class OrderIntent:
    """
    User's trading intent (before order creation)
    """
    wallet_id: UUID
    ticker: str
    market: Market
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    oracle_signal: Optional[dict] = None
    
    def __post_init__(self):
        # Validate limit price for LIMIT orders
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if self.limit_price is None:
                raise ValueError(f"{self.order_type} requires limit_price")
        
        # Validate stop price for STOP orders
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if self.stop_price is None:
                raise ValueError(f"{self.order_type} requires stop_price")
        
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")


@dataclass
class Order:
    """
    Order record (matches DB schema)
    """
    id: UUID
    wallet_id: UUID
    ticker: str
    market: Market
    side: OrderSide
    order_type: OrderType
    quantity: int
    filled_quantity: int = 0
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    avg_fill_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    rejection_reason: Optional[str] = None
    oracle_signal: Optional[dict] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED
    
    @property
    def is_partial(self) -> bool:
        return self.status == OrderStatus.PARTIAL
    
    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL)
    
    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity


@dataclass
class Quote:
    """
    Market quote snapshot
    """
    ticker: str
    market: Market
    price: Decimal
    bid: Optional[Decimal]
    ask: Optional[Decimal]
    volume: Optional[int]
    timestamp: datetime
    provider: str = "unknown"
    
    @property
    def mid(self) -> Decimal:
        """Mid-point of bid/ask"""
        if self.bid and self.ask:
            return (self.bid + self.ask) / Decimal('2')
        return self.price
    
    @property
    def spread(self) -> Optional[Decimal]:
        """Bid-ask spread"""
        if self.bid and self.ask:
            return self.ask - self.bid
        return None
    
    @property
    def spread_bps(self) -> Optional[Decimal]:
        """Spread in basis points"""
        spread = self.spread
        if spread and self.mid:
            return (spread / self.mid) * Decimal('10000')
        return None


@dataclass
class Trade:
    """
    Trade fill record (matches DB schema)
    """
    id: UUID
    order_id: UUID
    wallet_id: UUID
    ticker: str
    market: Market
    side: OrderSide
    quantity: int
    fill_price: Decimal
    slippage_bps: Optional[Decimal]
    commission: Decimal
    gross_amount: Decimal
    net_amount: Decimal
    quote_bid: Optional[Decimal]
    quote_ask: Optional[Decimal]
    quote_mid: Optional[Decimal]
    filled_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def from_fill(
        cls,
        order_id: UUID,
        wallet_id: UUID,
        ticker: str,
        market: Market,
        side: OrderSide,
        quantity: int,
        fill_price: Decimal,
        quote: Quote,
        commission: Decimal = Decimal('0')
    ) -> 'Trade':
        """Create trade from order fill"""
        gross_amount = Decimal(quantity) * fill_price
        
        # Commission adds to cost for BUY, subtracts from proceeds for SELL
        if side == OrderSide.BUY:
            net_amount = gross_amount + commission
        else:
            net_amount = gross_amount - commission
        
        # Calculate slippage from quote mid
        slippage_bps = None
        if quote.mid:
            slippage = fill_price - quote.mid
            slippage_bps = (slippage / quote.mid) * Decimal('10000')
        
        return cls(
            id=uuid4(),
            order_id=order_id,
            wallet_id=wallet_id,
            ticker=ticker,
            market=market,
            side=side,
            quantity=quantity,
            fill_price=fill_price,
            slippage_bps=slippage_bps,
            commission=commission,
            gross_amount=gross_amount,
            net_amount=net_amount,
            quote_bid=quote.bid,
            quote_ask=quote.ask,
            quote_mid=quote.mid
        )


@dataclass
class Position:
    """
    Position record (matches DB schema)
    
    NOTE: current_price and unrealised_pnl are NOT stored here
    They must be computed from latest market data
    """
    id: UUID
    wallet_id: UUID
    ticker: str
    market: Market
    quantity: int
    avg_entry_price: Decimal
    total_cost: Decimal
    realised_pnl: Decimal = Decimal('0')
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_open(self) -> bool:
        return self.quantity != 0 and self.closed_at is None
    
    def unrealised_pnl(self, current_price: Decimal) -> Decimal:
        """Compute unrealised PnL given current market price"""
        current_value = Decimal(self.quantity) * current_price
        return current_value - self.total_cost
    
    def unrealised_pnl_pct(self, current_price: Decimal) -> Decimal:
        """Compute unrealised PnL % given current market price"""
        if self.total_cost == 0:
            return Decimal('0')
        return (self.unrealised_pnl(current_price) / self.total_cost) * Decimal('100')


@dataclass
class Wallet:
    """
    Wallet record (matches DB schema)
    """
    id: UUID
    name: str
    capital_tier: str
    initial_balance: Decimal
    current_balance: Decimal
    reserved_balance: Decimal = Decimal('0')
    strategy_id: Optional[UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def buying_power(self) -> Decimal:
        """Available capital for new orders"""
        return self.current_balance - self.reserved_balance
    
    def can_afford(self, amount: Decimal) -> bool:
        """Check if wallet has sufficient buying power"""
        return self.buying_power >= amount
    
    def reserve(self, amount: Decimal) -> None:
        """Reserve capital for an order"""
        if amount > self.buying_power:
            raise ValueError(f"Insufficient buying power: {self.buying_power} < {amount}")
        self.reserved_balance += amount
    
    def release(self, amount: Decimal) -> None:
        """Release reserved capital"""
        self.reserved_balance -= amount
        if self.reserved_balance < 0:
            self.reserved_balance = Decimal('0')
    
    def debit(self, amount: Decimal) -> None:
        """Deduct from balance (BUY)"""
        if amount > self.current_balance:
            raise ValueError(f"Insufficient balance: {self.current_balance} < {amount}")
        self.current_balance -= amount
    
    def credit(self, amount: Decimal) -> None:
        """Add to balance (SELL)"""
        self.current_balance += amount
