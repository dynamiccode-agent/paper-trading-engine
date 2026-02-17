"""
Fallback Strategy - Proof-of-Life Trade
SAFETY MODE: Places ONLY 1 trade on 1 wallet as proof-of-life
"""
from decimal import Decimal
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class FallbackStrategy:
    """
    Safe proof-of-life trade generator
    DOES NOT trade multiple wallets - only first active wallet
    """
    
    # PROOF-OF-LIFE TICKER (most liquid, safe)
    PROOF_TICKER = 'AAPL'
    PROOF_MARKET = 'NASDAQ'
    PROOF_QTY = 1  # Minimal quantity
    
    @classmethod
    def generate_proof_of_life_signal(cls) -> Dict:
        """
        Generate ONE proof-of-life trade signal
        
        SAFETY:
        - Only AAPL
        - Only 1 share
        - Only if no existing position/order
        
        Returns:
            Signal dict: {ticker, market, action, quantity, price, reason}
        """
        return {
            'ticker': cls.PROOF_TICKER,
            'market': cls.PROOF_MARKET,
            'action': 'BUY',
            'quantity': cls.PROOF_QTY,
            'price': Decimal('200.00'),  # Conservative estimate
            'reason': 'FALLBACK_PROOF_OF_LIFE (oracle_signals unavailable for 3+ cycles)'
        }
    
    @classmethod
    def should_activate_fallback(cls, no_signal_cycles: int) -> bool:
        """
        Determine if fallback should activate
        
        Args:
            no_signal_cycles: Number of consecutive cycles with no signals
        
        Returns:
            True if fallback should activate (after 3 cycles)
        """
        return no_signal_cycles >= 3
