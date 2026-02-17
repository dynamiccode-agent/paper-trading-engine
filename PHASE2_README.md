# Phase 2: Strategy Integration + Realtime US Market Data

**Status:** ✅ Complete  
**Date:** 2026-02-17

---

## Overview

Phase 2 connects Oracle signals to the Paper Trading Engine with realtime US market data from Alpha Vantage Premium.

**Goal:** Simulate real NYSE/NASDAQ session trading with live signals.

---

## What's New

### 1. Realtime Market Data (Alpha Vantage Premium)
- **150 requests/minute** (upgraded from 5 req/min free tier)
- **Realtime US equities** entitlement enabled
- `entitlement=realtime` appended to all API calls
- Rate limiting with per-minute tracking
- Exponential backoff on 429 errors
- Circuit breaker (opens after 5 consecutive failures)

### 2. Market Session Detection
- Timezone-aware market hours checking
- NYSE/NASDAQ: 9:30 AM - 4:00 PM ET
- AEST → ET conversion handled automatically
- Weekend detection
- Time until next open calculation

### 3. Strategy Runner
- Queries Oracle database for top signals
- Filters: `market='US'`, `score >= threshold`, last 24 hours
- Risk rules enforcement
- Position sizing (equal weight or % buying power)
- Metrics snapshots after each cycle

### 4. Risk Rules
- **Max position size:** 20% of initial capital
- **Max concurrent positions:** 5 per wallet
- **Min cash reserve:** 10% of initial capital
- **No duplicate tickers** per wallet
- **Buying power checks** before order submission

### 5. Live Simulation Runner
- End-to-end script: signals → orders → fills → ledger
- Configurable cycles and intervals
- Market status checking
- Wallet summary + trade log output

---

## Architecture

### Market Data Flow (Single Source of Truth)

```
AlphaVantageProvider (realtime)
           ↓
       Cache (60s TTL)
           ↓
    Strategy Runner
           ↓
   Paper Trading Engine
```

**NEVER call API directly from:**
- Wallet loops
- Strategy loops
- Engine execution

**ONLY** MarketDataProvider → Cache → Engine consumes cache

---

## Usage

### Environment Variables

```bash
export DATABASE_URL="postgresql://user:pass@host/db"
export ORACLE_DATABASE_URL="postgresql://..."  # Optional, defaults to DATABASE_URL
export ALPHAVANTAGE_API_KEY="YOUR_PREMIUM_KEY"
```

⚠️ **NEVER hardcode or log the API key**

### Run Live Simulation

```bash
cd /Users/dynamiccode/clawd/quoterite/paper_trading
source ../oracle/venv312/bin/activate

python run_live_simulation.py \
    --cycles 5 \
    --interval 60 \
    --min-score 70
```

**Options:**
- `--cycles N` - Number of execution cycles (default: 5)
- `--interval SECONDS` - Seconds between cycles (default: 60)
- `--min-score SCORE` - Minimum Oracle signal score (default: 70)

---

## Market Session Detection

### Usage

```python
from lib.market_session import is_market_open, MarketSession

# Quick check
if is_market_open('US'):
    # Execute strategy
    pass

# Detailed status
status = MarketSession.get_market_status('US')
print(status)
# {
#     'market': 'US',
#     'is_open': False,
#     'local_time': '2026-02-17 04:09:24 EST',
#     'timezone': 'America/New_York',
#     'next_open': '5h 20m',
#     'seconds_until_open': 19235.42
# }
```

### Supported Markets
- `'US'` - NYSE/NASDAQ (9:30 AM - 4:00 PM ET)
- `'ASX'` - Australian Securities Exchange (10:00 AM - 4:00 PM Sydney)
- `'TSX'` - Toronto Stock Exchange (9:30 AM - 4:00 PM Toronto)

---

## Strategy Runner

### Configuration

```python
from lib.strategy_runner import StrategyRunner

runner = StrategyRunner(
    engine=paper_trading_engine,
    oracle_db_url=ORACLE_DATABASE_URL,
    min_signal_score=70,         # Min Oracle score
    max_signals=5,               # Top N signals
    position_sizing='equal_weight'  # or 'percent_buying_power'
)
```

### Execute Strategy

```python
result = runner.execute_strategy_for_wallet(wallet_id)

# Returns:
# {
#     'wallet_id': UUID,
#     'signals_processed': 5,
#     'orders_submitted': 3,
#     'orders_rejected': 2,
#     'rejections': [
#         {'ticker': 'AAPL', 'reason': 'DUPLICATE_POSITION'},
#         {'ticker': 'MSFT', 'reason': 'MAX_POSITIONS_REACHED (5/5)'}
#     ]
# }
```

### Snapshot Metrics

```python
runner.snapshot_metrics(wallet_id)
# Stores daily metrics to strategy_metrics table:
# - equity
# - pnl (realised + unrealised)
# - win_rate
# - trade_count
```

---

## Risk Rules

### Validation Logic

```python
from lib.strategy_runner import RiskRules

is_valid, reason = RiskRules.validate_order(
    wallet=wallet,
    ticker='AAPL',
    estimated_cost=Decimal('2000.00'),
    current_positions=4
)

if not is_valid:
    print(f"Order rejected: {reason}")
    # Possible reasons:
    # - MAX_POSITIONS_REACHED (5/5)
    # - POSITION_TOO_LARGE ($3000 > $2000)
    # - INSUFFICIENT_BUYING_POWER (need reserve: $1000)
```

### Rules

| Rule | Default | Description |
|------|---------|-------------|
| `MAX_POSITION_PCT` | 20% | Max % of initial capital per position |
| `MAX_CONCURRENT_POSITIONS` | 5 | Max open positions per wallet |
| `MIN_BUYING_POWER_PCT` | 10% | Min % cash reserve |

---

## Alpha Vantage Premium

### Realtime Entitlement

All requests include `entitlement=realtime`:

```
https://www.alphavantage.co/query?
    function=GLOBAL_QUOTE&
    symbol=AAPL&
    entitlement=realtime&      ← REQUIRED
    apikey=YOUR_KEY
```

### Rate Limiting

**Premium Limits:**
- 150 requests/minute
- Provider tracks requests per minute
- Safety margin: stops at 145 req/min
- Auto-resets every 60 seconds

**Backoff Strategy:**
- 429 error → exponential backoff (2^n seconds, max 60s)
- Retry once after backoff
- Fail loudly if still rejected

### Circuit Breaker

**Triggers:**
- 5 consecutive failures (API errors, timeouts, rate limits)

**Behavior:**
- Opens circuit → all requests fail immediately
- Prevents cascading failures
- Logs: `🚨 CIRCUIT BREAKER OPEN`

**Recovery:**
- Manual restart required (circuit doesn't auto-close)

---

## Example Output

```
======================================================================
LIVE PAPER TRADING SIMULATION
======================================================================

📊 Market Status:
   Market: US
   Status: 🟢 OPEN
   Local Time: 2026-02-17 09:45:00 EST

🌐 Initializing market data provider...
✅ AlphaVantage Premium (realtime enabled)

⚙️  Initializing paper trading engine...
✅ Engine ready

📈 Initializing strategy runner...
✅ Strategy ready (min_score: 70)

💼 Setting up test wallet...
✅ Using existing test wallet: a1b2c3d4...

======================================================================
WALLET: LiveSim-Test-10K
======================================================================
Balance: $10,000.00
Buying Power: $10,000.00
Equity: $10,000.00
PnL: $0.00 (+0.00%)
Open Positions: 0

🔄 Starting execution loop (5 cycles, 60s interval)
======================================================================


======================================================================
CYCLE 1/5
======================================================================
📊 Oracle signals: 5 found (market: US, min_score: 70)
📝 Submitting: BUY 11 AAPL @ MARKET (score: 85.5)
✅ Order submitted: xyz-123 (SUBMITTED)
📝 Submitting: BUY 18 MSFT @ MARKET (score: 82.3)
✅ Order submitted: xyz-456 (SUBMITTED)
📝 Submitting: BUY 25 GOOGL @ MARKET (score: 78.1)
✅ Order submitted: xyz-789 (SUBMITTED)

📊 Execution Results:
   Signals Processed: 5
   Orders Submitted: 3
   Orders Rejected: 2

⚠️  Rejections:
      TSLA: MAX_POSITIONS_REACHED (5/5)
      AMZN: INSUFFICIENT_BUYING_POWER (need reserve: $1000)

======================================================================
WALLET: LiveSim-Test-10K
======================================================================
Balance: $7,145.32
Buying Power: $6,145.32
Equity: $10,012.45
PnL: $12.45 (+0.12%)
Open Positions: 3

POSITIONS:
  AAPL: 11 shares @ $180.50 → $181.20 (+0.39%)
  MSFT: 18 shares @ $370.25 → $369.80 (-0.12%)
  GOOGL: 25 shares @ $140.80 → $141.10 (+0.21%)

RECENT TRADES:
  09:45:12 - BUY 11 AAPL @ $180.6073 (slip: 5.9 bps)
  09:45:14 - BUY 18 MSFT @ $370.3195 (slip: 1.9 bps)
  09:45:16 - BUY 25 GOOGL @ $140.8805 (slip: 5.7 bps)

⏳ Waiting 60s until next cycle...
```

---

## Testing

### Test Market Session

```bash
python -c "
from lib.market_session import MarketSession
import json
status = MarketSession.get_market_status('US')
print(json.dumps(status, indent=2, default=str))
"
```

### Test Strategy Runner (Dry Run)

```bash
python -c "
from lib.strategy_runner import StrategyRunner
from lib.engine import PaperTradingEngine
from lib.market_data import MockMarketDataProvider
import os

# Use mock provider for testing
market_data = MockMarketDataProvider()
engine = PaperTradingEngine(os.environ['DATABASE_URL'], market_data)
runner = StrategyRunner(engine, os.environ['DATABASE_URL'], min_signal_score=70)

signals = runner.get_oracle_signals(market='US')
print(f'Found {len(signals)} signals')
for s in signals:
    print(f\"  {s['ticker']}: {s['score']}\")
"
```

---

## Next Phase: Batch Wallets + Parallel Execution

**Phase 3 Goals:**
- Create 50+ wallets (10× each tier: 1k, 10k, 20k, 40k, 50k)
- Run strategies in parallel
- Aggregate metrics across wallets
- Statistical validation (which tier + strategy wins?)

**Phase 4 Goals:**
- UI dashboard (Parallax integration)
- Equity curve visualization
- Performance heatmaps
- Probability scoring engine

---

## Files Added

```
paper_trading/
├── lib/
│   ├── market_data.py          # Updated: realtime entitlement
│   ├── market_session.py       # NEW: Market hours detection
│   └── strategy_runner.py      # NEW: Oracle → Engine bridge
├── run_live_simulation.py      # NEW: Live simulation script
├── requirements.txt            # Updated: added pytz
└── PHASE2_README.md            # This file
```

---

## Troubleshooting

### "Circuit breaker OPEN"
- Check Alpha Vantage API status
- Verify API key is valid
- Check rate limits (150 req/min)
- Restart simulation to reset circuit

### "Market closed"
- Use `MarketSession.get_market_status('US')` to check hours
- US market: 9:30 AM - 4:00 PM ET (Mon-Fri)
- Simulation runs but orders may not be realistic

### "No signals found"
- Check Oracle database has recent data (`last_updated > NOW() - INTERVAL '24 hours'`)
- Lower `--min-score` threshold
- Verify `market='US'` in Oracle instruments table

### "Order rejected: INSUFFICIENT_FUNDS"
- Check wallet buying power
- Reduce `max_signals` (fewer positions = lower capital required)
- Increase wallet initial_balance

---

## Success Criteria

✅ **Phase 2 Complete When:**
- Oracle signals → Orders → Fills → Ledger flow working
- No API abuse (rate limiting working)
- No drift in equity calculations
- No duplicate positions
- Risk rules enforced
- Metrics snapshots storing correctly

---

**Phase 2 Status:** ✅ COMPLETE  
**Ready for:** Phase 3 (Batch Wallets + Parallel Execution)
