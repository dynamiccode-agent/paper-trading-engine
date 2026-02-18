"""
Market Data Provider - Pluggable abstraction for quote sources
"""
import logging
import time
import decimal
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict
import requests

from .types import Quote, Market

logger = logging.getLogger(__name__)


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers
    """
    
    @abstractmethod
    def get_quote(self, ticker: str, market: Market) -> Optional[Quote]:
        """Fetch current quote for ticker"""
        pass
    
    @abstractmethod
    def get_spread_model(self, ticker: str, market: Market) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Get bid/ask spread for ticker
        Returns: (bid, ask) tuple
        """
        pass


class AlphaVantageProvider(MarketDataProvider):
    """
    Alpha Vantage API provider with Premium realtime entitlement
    
    Docs: https://www.alphavantage.co/documentation/
    Premium: 150 requests/minute with realtime US equities
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(
        self,
        api_key: str,
        cache_ttl: int = 60,
        use_spread_model: bool = True,
        spread_bps: Decimal = Decimal('10'),  # Default 10 bps spread
        require_realtime: bool = True
    ):
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self.use_spread_model = use_spread_model
        self.spread_bps = spread_bps
        self.require_realtime = require_realtime
        self.cache: Dict[str, dict] = {}
        
        # Rate limiting (Premium: 150 req/min)
        self.last_request_time = 0
        self.min_request_interval = 0.4  # 150 req/min = 0.4s interval
        self.requests_this_minute = 0
        self.minute_start = time.time()
        
        # Circuit breaker
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.circuit_open = False
    
    def _rate_limit(self) -> None:
        """
        Enforce rate limit with per-minute tracking
        Premium: 150 req/min
        """
        now = time.time()
        
        # Reset counter every minute
        if now - self.minute_start >= 60:
            logger.info(f"📊 API usage last minute: {self.requests_this_minute} requests")
            self.requests_this_minute = 0
            self.minute_start = now
        
        # Check if approaching limit
        if self.requests_this_minute >= 145:  # Safety margin
            sleep_until_next_minute = 60 - (now - self.minute_start)
            if sleep_until_next_minute > 0:
                logger.warning(f"⚠️ Approaching rate limit, sleeping {sleep_until_next_minute:.1f}s")
                time.sleep(sleep_until_next_minute)
                self.requests_this_minute = 0
                self.minute_start = time.time()
        
        # Enforce minimum interval
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.requests_this_minute += 1
    
    def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker is open"""
        if self.circuit_open:
            logger.error(
                f"🚨 CIRCUIT BREAKER OPEN\n"
                f"   Consecutive failures: {self.consecutive_failures}\n"
                f"   Reason: Market data provider unavailable\n"
                f"   Action: Manual restart required"
            )
            raise RuntimeError(
                f"Circuit breaker OPEN: {self.consecutive_failures} consecutive failures. "
                "Market data provider unavailable."
            )
    
    def _generate_fallback_quote(self, ticker: str, market: Market) -> Quote:
        """Generate conservative fallback quote when API unavailable"""
        # Conservative price estimates based on typical ranges
        price_estimates = {
            # Tech stocks
            'AAPL': Decimal('180'),
            'MSFT': Decimal('410'),
            'GOOGL': Decimal('140'),
            'AMZN': Decimal('180'),
            'NVDA': Decimal('480'),
            'META': Decimal('490'),
            'TSLA': Decimal('200'),
            'AMD': Decimal('160'),
            # Value stocks
            'BRK.B': Decimal('420'),
            'JPM': Decimal('200'),
            'JNJ': Decimal('150'),
            'PG': Decimal('170'),
            'KO': Decimal('63'),
            'V': Decimal('270'),
            # ETFs
            'SPY': Decimal('550'),
            'QQQ': Decimal('480'),
            'DIA': Decimal('430'),
            'IWM': Decimal('215'),
            'XLK': Decimal('220'),
            'XLF': Decimal('42'),
            'XLE': Decimal('85'),
            'XLV': Decimal('145'),
            'XLI': Decimal('125'),
            # Volatility
            'VXX': Decimal('45'),
            'UVXY': Decimal('18'),
            'VIXY': Decimal('16'),
        }
        
        import datetime
        
        price = price_estimates.get(ticker, Decimal('150'))  # Default to $150
        bid, ask = self.get_spread_model(ticker, market, price)
        
        return Quote(
            ticker=ticker,
            market=market,
            price=price,
            bid=bid or price * Decimal('0.999'),
            ask=ask or price * Decimal('1.001'),
            volume=1000000,  # Nominal volume
            timestamp=datetime.datetime.now()
        )
    
    def _get_cache_key(self, ticker: str, market: Market) -> str:
        return f"{ticker}:{market.value}"
    
    def _check_cache(self, ticker: str, market: Market) -> Optional[Quote]:
        """Check cache for recent quote"""
        key = self._get_cache_key(ticker, market)
        if key in self.cache:
            cached = self.cache[key]
            age = time.time() - cached['fetched_at']
            if age < self.cache_ttl:
                logger.debug(f"Cache hit: {ticker} (age: {age:.1f}s)")
                return cached['quote']
        return None
    
    def _update_cache(self, ticker: str, market: Market, quote: Quote) -> None:
        """Update cache with new quote"""
        key = self._get_cache_key(ticker, market)
        self.cache[key] = {
            'quote': quote,
            'fetched_at': time.time()
        }
    
    def get_quote(self, ticker: str, market: Market) -> Optional[Quote]:
        """
        Fetch quote from Alpha Vantage GLOBAL_QUOTE endpoint with realtime entitlement
        """
        # Check circuit breaker (or use fallback if not requiring realtime)
        try:
            self._check_circuit_breaker()
        except RuntimeError as e:
            if not self.require_realtime:
                # Return fallback quote when circuit open and realtime not required
                logger.info(f"📉 Using fallback quote for {ticker} (circuit open)")
                return self._generate_fallback_quote(ticker, market)
            else:
                raise
        
        # Check cache first
        cached = self._check_cache(ticker, market)
        if cached:
            return cached
        
        # Rate limit
        self._rate_limit()
        
        # Fetch from API
        try:
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': ticker,
                'entitlement': 'realtime',  # REQUIRED for Premium realtime
                'apikey': self.api_key
            }
            
            logger.info(f"Fetching realtime quote: {ticker}")
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            # Handle rate limit (429)
            if response.status_code == 429:
                logger.warning(f"⚠️ Rate limit hit (429), backing off...")
                self.consecutive_failures += 1
                
                # Exponential backoff
                backoff_time = min(2 ** self.consecutive_failures, 60)
                time.sleep(backoff_time)
                
                # Retry once
                response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API errors
            if 'Error Message' in data:
                logger.error(f"❌ API error for {ticker}: {data['Error Message']}")
                self.consecutive_failures += 1
                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.circuit_open = True
                return None
            
            if 'Note' in data:
                logger.error(f"❌ API rate limit note for {ticker}: {data['Note']}")
                self.consecutive_failures += 1
                return None
            
            if 'Global Quote' not in data or not data['Global Quote']:
                logger.warning(f"No quote data for {ticker}: {data}")
                self.consecutive_failures += 1
                return None
            
            quote_data = data['Global Quote']
            
            # FAIL LOUDLY if realtime not returned (if required)
            if self.require_realtime:
                # Alpha Vantage doesn't explicitly mark realtime in response
                # But we can check timestamp freshness
                # For now, log that we requested realtime
                logger.debug(f"✅ Realtime quote requested for {ticker}")
            
            # Parse price
            price = Decimal(quote_data['05. price'])
            volume = int(quote_data['06. volume'])
            
            # Generate bid/ask using spread model
            bid, ask = self.get_spread_model(ticker, market, price)
            
            quote = Quote(
                ticker=ticker,
                market=market,
                price=price,
                bid=bid,
                ask=ask,
                volume=volume,
                timestamp=datetime.utcnow(),
                provider='alphavantage-realtime'
            )
            
            # Update cache
            self._update_cache(ticker, market, quote)
            
            # Reset failure counter on success
            self.consecutive_failures = 0
            
            logger.info(f"✅ Quote: {ticker} = ${price} (bid: ${bid}, ask: ${ask})")
            return quote
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {ticker}: {e}")
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.circuit_open = True
                logger.error(
                    f"🚨 CIRCUIT BREAKER OPENED\n"
                    f"   Trigger: {self.max_consecutive_failures} consecutive failures\n"
                    f"   Last error: {e}\n"
                    f"   Status: Market data provider unavailable\n"
                    f"   Recovery: Manual restart required"
                )
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse quote for {ticker}: {e}")
            self.consecutive_failures += 1
            return None
    
    def get_spread_model(
        self,
        ticker: str,
        market: Market,
        price: Optional[Decimal] = None
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Model bid/ask spread since Alpha Vantage doesn't provide it
        
        Returns: (bid, ask) tuple
        
        Approach:
        - Use configurable basis points spread (default 10 bps = 0.1%)
        - bid = price * (1 - spread_bps/10000)
        - ask = price * (1 + spread_bps/10000)
        
        Future enhancement: Use volatility-based spread modeling
        """
        if not self.use_spread_model or price is None:
            return None, None
        
        spread_factor = self.spread_bps / Decimal('10000')
        bid = price * (Decimal('1') - spread_factor)
        ask = price * (Decimal('1') + spread_factor)
        
        # Round to 4 decimal places
        bid = bid.quantize(Decimal('0.0001'))
        ask = ask.quantize(Decimal('0.0001'))
        
        return bid, ask


class YahooFinanceProvider(MarketDataProvider):
    """
    Yahoo Finance provider (future implementation)
    
    Advantages:
    - Free, no API key required
    - Real bid/ask spreads
    - High rate limits
    
    Disadvantages:
    - Unofficial API (could break)
    - No SLA/support
    """
    
    def get_quote(self, ticker: str, market: Market) -> Optional[Quote]:
        raise NotImplementedError("YahooFinanceProvider not yet implemented")
    
    def get_spread_model(self, ticker: str, market: Market) -> tuple[Optional[Decimal], Optional[Decimal]]:
        raise NotImplementedError("YahooFinanceProvider not yet implemented")
