"""
ASX Fallback Strategy - Proof-of-Life for ASX Trading
SAFETY: Only 1 wallet, only 1 trade, $500 AUD minimum parcel
"""
from decimal import Decimal
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ASXFallbackStrategy:
    """
    ASX-specific fallback with minimum marketable parcel enforcement
    """
    
    # ASX blue-chip tickers (highly liquid)
    ASX_TICKERS = [
        'BHP.AX',   # BHP Group
        'CBA.AX',   # Commonwealth Bank
        'NAB.AX',   # National Australia Bank
        'WBC.AX',   # Westpac
        'ANZ.AX',   # ANZ Bank
        'WES.AX',   # Wesfarmers
        'WOW.AX',   # Woolworths
        'RIO.AX',   # Rio Tinto
        'CSL.AX',   # CSL Limited
        'FMG.AX',   # Fortescue Metals
    ]
    
    # ASX minimum marketable parcel
    MIN_PARCEL_AUD = Decimal('500.00')
    
    # Estimated prices for quantity calculation (conservative)
    ESTIMATED_PRICES = {
        'BHP.AX': Decimal('42.00'),
        'CBA.AX': Decimal('130.00'),
        'NAB.AX': Decimal('35.00'),
        'WBC.AX': Decimal('28.00'),
        'ANZ.AX': Decimal('29.00'),
        'WES.AX': Decimal('65.00'),
        'WOW.AX': Decimal('35.00'),
        'RIO.AX': Decimal('120.00'),
        'CSL.AX': Decimal('280.00'),
        'FMG.AX': Decimal('18.00'),
    }
    
    @classmethod
    def generate_asx_proof_signal(cls, wallet_name: str) -> Dict:
        """
        Generate ONE ASX proof-of-life signal
        
        SAFETY MODE:
        - Quantity = 1 (minimal proof-of-life)
        - LIMIT order (not MARKET)
        - Blue-chip ticker only
        - Ignores $500 minimum for initial proof
        
        Args:
            wallet_name: Wallet name (for ticker selection)
        
        Returns:
            Signal dict with ticker, quantity, limit_price
        """
        # Pick ticker based on wallet hash
        ticker_index = hash(wallet_name) % len(cls.ASX_TICKERS)
        ticker = cls.ASX_TICKERS[ticker_index]
        
        # Get estimated price
        estimated_price = cls.ESTIMATED_PRICES.get(ticker, Decimal('50.00'))
        
        # SAFETY MODE: qty = 1 for proof-of-life
        quantity = 1
        
        logger.info(f"🇦🇺 ASX proof signal: {ticker} x{quantity} @ ${estimated_price} = ${quantity * estimated_price}")
        
        return {
            'ticker': ticker,
            'market': 'ASX',
            'action': 'BUY',
            'quantity': quantity,
            'limit_price': estimated_price,  # Use LIMIT order
            'reason': 'ASX_PROOF_OF_LIFE_QTY1'
        }
    
    @classmethod
    def should_activate_fallback(cls, no_signal_cycles: int) -> bool:
        """
        ASX fallback: Activate after 3 cycles (same as US)
        """
        return no_signal_cycles >= 3
    
    @classmethod
    def validate_parcel(cls, quantity: int, price: Decimal) -> tuple[bool, Optional[str]]:
        """
        Validate ASX minimum marketable parcel
        
        Args:
            quantity: Number of shares
            price: Price per share
        
        Returns:
            (is_valid, error_message)
        """
        parcel_value = quantity * price
        
        if parcel_value < cls.MIN_PARCEL_AUD:
            return False, f"BELOW_MIN_PARCEL (${parcel_value} < ${cls.MIN_PARCEL_AUD})"
        
        return True, None
