# Fallback Strategy Fix

## Problem
Oracle signals table (`instruments`) doesn't exist or has no data.  
Strategy runner returns `NO_SIGNALS` every cycle with no trades.

## Solution Applied

### 1. Created Fallback Strategy
**File:** `lib/fallback_strategy.py`

**Logic:**
- If no Oracle signals for 3+ consecutive cycles → activate fallback
- Place 1 minimal test trade per wallet (1 share of large-cap stock)
- Tickers: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, WMT
- Each wallet gets a different ticker (hash-based selection)

### 2. Next Step: Integrate Into Runner
**Modify:** `lib/strategy_runner.py`

**Add to __init__:**
```python
self.no_signal_cycles = 0  # Track consecutive cycles with no signals
```

**Modify execute_strategy_for_wallet:**
```python
# Get Oracle signals
signals = self.get_oracle_signals(market='US')

if not signals:
    self.no_signal_cycles += 1
    logger.warning(f"No signals found (cycle {self.no_signal_cycles})")
    
    # Activate fallback after 3 cycles
    if FallbackStrategy.should_activate_fallback(self.no_signal_cycles):
        logger.info("🔄 FALLBACK ACTIVATED - Placing test trade")
        test_trade = FallbackStrategy.get_test_trade_for_wallet(
            wallet.name,
            wallet.buying_power
        )
        # Execute test trade...
        self.no_signal_cycles = 0  # Reset after fallback
    
    return {'error': 'NO_SIGNALS'}
else:
    self.no_signal_cycles = 0  # Reset counter when signals found
```

### 3. Tyler's Request Met
- ✅ If oracle_signals empty for 3 cycles → 1 minimal test trade per wallet
- ✅ Ensures trading activity even without Oracle pipeline
- ✅ Uses safe, liquid tickers (large caps)

### 4. Permanent Fix Needed
**Create instruments table:**
- PostgreSQL schema for Oracle signals
- Populate with real market analysis
- Connect Oracle signal generator job

## Status
- Fallback code written ✅
- Integration pending (requires runner modification)
- Will deploy after Tyler confirms approach
