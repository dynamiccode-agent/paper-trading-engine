"""
Fallback Strategy - Daily Trading for Each Wallet
Generates safe signals when Oracle is unavailable
"""
from decimal import Decimal
from typing import Dict, List
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

class FallbackStrategy:
    """
    Safe daily fallback trade generator
    Each wallet gets 1 trade/day when Oracle signals unavailable
    """
    
    # Liquid, safe tickers by strategy type
    STRATEGY_TICKERS = {
        'Momentum-Long': ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'META'],
        'Value-Deep': ['BRK.B', 'JPM', 'JNJ', 'PG', 'KO'],
        'Breakout-Tech': ['AAPL', 'GOOGL', 'AMZN', 'NVDA', 'AMD'],
        'Mean-Reversion': ['SPY', 'QQQ', 'DIA', 'IWM', 'XLF'],
        'Growth-Quality': ['MSFT', 'AAPL', 'GOOGL', 'AMZN', 'V'],
        'Dividend-Yield': ['VZ', 'T', 'PFE', 'XOM', 'CVX'],
        'Small-Cap-Growth': ['ROKU', 'SQ', 'PLTR', 'SNAP', 'LCID'],
        'Sector-Rotation': ['XLK', 'XLF', 'XLE', 'XLV', 'XLI'],
        'Volatility-Long': ['VXX', 'UVXY', 'VIXY', 'SVXY', 'SPY'],
        'Options-Hedged': ['SPY', 'QQQ', 'AAPL', 'MSFT', 'TSLA']
    }
    
    # Default tickers if strategy unknown
    DEFAULT_TICKERS = ['AAPL', 'MSFT', 'SPY', 'QQQ', 'GOOGL']
    
    @classmethod
    def generate_daily_signal(cls, wallet_name: str, existing_tickers: set) -> Dict:
        """
        Generate ONE daily fallback signal per wallet
        
        Args:
            wallet_name: Name of wallet (e.g., "Momentum-Long")
            existing_tickers: Set of tickers already in portfolio
        
        Returns:
            Signal dict: {ticker, market, action, quantity, price, reason}
        """
        # Get strategy-appropriate tickers
        tickers = cls.STRATEGY_TICKERS.get(wallet_name, cls.DEFAULT_TICKERS)
        
        # Filter out existing positions
        available = [t for t in tickers if t not in existing_tickers]
        
        if not available:
            # All tickers already held, use default pool
            available = [t for t in cls.DEFAULT_TICKERS if t not in existing_tickers]
        
        if not available:
            # Still none? Just pick first strategy ticker
            available = [tickers[0]]
        
        # Pick random ticker from available
        ticker = random.choice(available)
        
        # Determine market (ETFs trade on NYSE/NASDAQ)
        if ticker in ['SPY', 'DIA', 'IWM']:
            market = 'NYSE'
        elif ticker.startswith('XL'):
            market = 'NYSE'  # Sector ETFs trade on NYSE
        else:
            market = 'NASDAQ'  # Default for stocks and QQQ, volatility ETFs
        
        # Conservative quantity based on strategy
        if wallet_name == 'Volatility-Long':
            qty = 5  # Volatility ETFs are cheaper
        elif wallet_name == 'Small-Cap-Growth':
            qty = 10  # Small caps are cheaper
        elif 'Dividend' in wallet_name:
            qty = 15  # Build dividend positions
        else:
            qty = 1  # Safe default
        
        return {
            'ticker': ticker,
            'market': market,
            'action': 'BUY',
            'quantity': qty,
            'price': Decimal('150.00'),  # Conservative estimate
            'reason': f'FALLBACK_DAILY ({wallet_name} strategy - Oracle unavailable)'
        }
    
    @classmethod
    def should_trade_today(cls, wallet_id: str, conn) -> bool:
        """
        Check if wallet has already traded today
        
        Args:
            wallet_id: Wallet UUID
            conn: Database connection
        
        Returns:
            True if wallet should trade (no trades today yet)
        """
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as trade_count
                FROM trades
                WHERE wallet_id = %s
                  AND filled_at >= CURRENT_DATE
            """, (wallet_id,))
            result = cur.fetchone()
            
            trades_today = result[0] if result else 0
            return trades_today == 0
    
    @classmethod
    def should_activate_fallback(cls, no_signal_cycles: int) -> bool:
        """
        Determine if fallback should activate
        
        Args:
            no_signal_cycles: Number of consecutive cycles with no signals
        
        Returns:
            True if fallback should activate (immediately - Oracle unavailable)
        """
        # Activate immediately if Oracle has no signals
        return no_signal_cycles >= 1
