"""
Mock Market Data Provider - For testing without API keys
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .types import Quote, Market
from .market_data import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    """
    Mock provider with fake but realistic data
    """
    
    MOCK_PRICES = {
        'AAPL': Decimal('180.50'),
        'MSFT': Decimal('370.25'),
        'GOOGL': Decimal('140.80'),
        'AMZN': Decimal('175.30'),
        'TSLA': Decimal('245.60'),
        'BHP': Decimal('53.20'),
        'WBC': Decimal('40.85'),
        'NAB': Decimal('38.50'),
    }
    
    def __init__(self, spread_bps: Decimal = Decimal('10')):
        self.spread_bps = spread_bps
    
    def get_quote(self, ticker: str, market: Market) -> Optional[Quote]:
        """Return mock quote"""
        if ticker not in self.MOCK_PRICES:
            return None
        
        price = self.MOCK_PRICES[ticker]
        bid, ask = self.get_spread_model(ticker, market, price)
        
        return Quote(
            ticker=ticker,
            market=market,
            price=price,
            bid=bid,
            ask=ask,
            volume=1000000,
            timestamp=datetime.utcnow(),
            provider='mock'
        )
    
    def get_spread_model(
        self,
        ticker: str,
        market: Market,
        price: Optional[Decimal] = None
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Generate bid/ask from price"""
        if price is None:
            price = self.MOCK_PRICES.get(ticker)
        
        if price is None:
            return None, None
        
        spread_factor = self.spread_bps / Decimal('10000')
        bid = price * (Decimal('1') - spread_factor)
        ask = price * (Decimal('1') + spread_factor)
        
        return (
            bid.quantize(Decimal('0.0001')),
            ask.quantize(Decimal('0.0001'))
        )
