"""
Market Session Detection - Timezone-aware market hours checking
"""
import logging
from datetime import datetime, time as dt_time
from typing import Optional
import pytz

logger = logging.getLogger(__name__)


class MarketSession:
    """
    Market hours checker with timezone awareness
    """
    
    # Market timezones
    TIMEZONES = {
        'US': 'America/New_York',  # NYSE/NASDAQ
        'ASX': 'Australia/Sydney',
        'TSX': 'America/Toronto'
    }
    
    # Market hours (local time)
    MARKET_HOURS = {
        'US': {
            'open': dt_time(9, 30),   # 9:30 AM ET
            'close': dt_time(16, 0)    # 4:00 PM ET
        },
        'ASX': {
            'open': dt_time(10, 0),    # 10:00 AM Sydney
            'close': dt_time(16, 0)    # 4:00 PM Sydney
        },
        'TSX': {
            'open': dt_time(9, 30),    # 9:30 AM Toronto
            'close': dt_time(16, 0)    # 4:00 PM Toronto
        }
    }
    
    # Market days (Monday = 0, Sunday = 6)
    TRADING_DAYS = [0, 1, 2, 3, 4]  # Mon-Fri
    
    @classmethod
    def is_market_open(cls, market: str, now: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open
        
        Args:
            market: 'US', 'ASX', or 'TSX'
            now: Optional datetime (defaults to current time)
        
        Returns:
            True if market is open, False otherwise
        """
        if now is None:
            now = datetime.utcnow()
        
        if market not in cls.TIMEZONES:
            logger.error(f"Unknown market: {market}")
            return False
        
        # Get market timezone
        tz = pytz.timezone(cls.TIMEZONES[market])
        market_time = now.replace(tzinfo=pytz.UTC).astimezone(tz)
        
        # Check if it's a trading day (Mon-Fri)
        if market_time.weekday() not in cls.TRADING_DAYS:
            logger.debug(f"{market} closed: Weekend")
            return False
        
        # Get market hours
        hours = cls.MARKET_HOURS[market]
        current_time = market_time.time()
        
        # Check if within trading hours
        is_open = hours['open'] <= current_time < hours['close']
        
        if is_open:
            logger.debug(f"✅ {market} market OPEN ({market_time.strftime('%H:%M %Z')})")
        else:
            logger.debug(f"❌ {market} market CLOSED ({market_time.strftime('%H:%M %Z')})")
        
        return is_open
    
    @classmethod
    def time_until_open(cls, market: str, now: Optional[datetime] = None) -> Optional[float]:
        """
        Calculate seconds until market opens
        
        Returns:
            Seconds until open, or None if currently open
        """
        if cls.is_market_open(market, now):
            return None
        
        if now is None:
            now = datetime.utcnow()
        
        tz = pytz.timezone(cls.TIMEZONES[market])
        market_time = now.replace(tzinfo=pytz.UTC).astimezone(tz)
        
        hours = cls.MARKET_HOURS[market]
        
        # Create datetime for next market open
        next_open = market_time.replace(
            hour=hours['open'].hour,
            minute=hours['open'].minute,
            second=0,
            microsecond=0
        )
        
        # If past today's open, move to next trading day
        if market_time.time() >= hours['close']:
            # Move to next day
            next_open = next_open.replace(day=next_open.day + 1)
            
            # Skip weekends
            while next_open.weekday() not in cls.TRADING_DAYS:
                next_open = next_open.replace(day=next_open.day + 1)
        
        # Calculate seconds
        delta = (next_open - market_time).total_seconds()
        return delta
    
    @classmethod
    def get_market_status(cls, market: str) -> dict:
        """
        Get detailed market status
        
        Returns:
            {
                'market': str,
                'is_open': bool,
                'local_time': str,
                'timezone': str,
                'next_open': Optional[str],
                'seconds_until_open': Optional[float]
            }
        """
        now = datetime.utcnow()
        tz = pytz.timezone(cls.TIMEZONES[market])
        market_time = now.replace(tzinfo=pytz.UTC).astimezone(tz)
        
        is_open = cls.is_market_open(market, now)
        seconds_until = cls.time_until_open(market, now)
        
        status = {
            'market': market,
            'is_open': is_open,
            'local_time': market_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'timezone': cls.TIMEZONES[market],
            'next_open': None,
            'seconds_until_open': seconds_until
        }
        
        if seconds_until:
            hours = int(seconds_until // 3600)
            minutes = int((seconds_until % 3600) // 60)
            status['next_open'] = f"{hours}h {minutes}m"
        
        return status


def is_market_open(market: str) -> bool:
    """
    Convenience function: Check if market is currently open
    
    Args:
        market: 'US', 'ASX', or 'TSX'
    
    Returns:
        True if market is open, False otherwise
    """
    return MarketSession.is_market_open(market)
