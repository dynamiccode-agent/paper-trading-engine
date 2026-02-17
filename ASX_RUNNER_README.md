# ASX Paper Trading Runner - Documentation

## Overview

Separate ASX runner for proof-of-life trading on Australian Securities Exchange.

**Key Features:**
- ✅ Separate process from US runner
- ✅ ASX market hours only (10:00-16:00 AEST)
- ✅ 1 wallet proof-of-life mode
- ✅ $500 AUD minimum marketable parcel
- ✅ LIMIT orders (not MARKET)
- ✅ MVJ (Minimal Viable Journal) recording
- ✅ Own PID and logs

---

## Start ASX Trading

### Command:
```bash
cd /Users/dynamiccode/clawd/quoterite/paper_trading
bash start_asx_trading.sh
```

### Output:
```
=========================================
ASX PAPER TRADING STARTUP
=========================================
Time: Wed Feb 18 10:00:00 AEST 2026
Market: ASX (10:00-16:00 AEST)
Mode: PROOF-OF-LIFE (1 wallet, $500 AUD min)
=========================================
Starting ASX runner...
✓ ASX Runner started (PID: 12345)

=========================================
✅ ASX TRADING ACTIVE
=========================================
  ASX Runner PID: 12345

Monitor:
  tail -f logs/runner_asx.log

Stop:
  kill $(cat logs/runner_asx.pid)
=========================================
```

---

## Verify ASX Trading

### Command:
```bash
cd /Users/dynamiccode/clawd/quoterite/paper_trading
bash verify_asx_trades.sh
```

### Expected Output:
```
=========================================
ASX TRADE VERIFICATION
=========================================
Time: Wed Feb 18 10:05:00 AEST 2026

✅ ASX Runner: ACTIVE (PID: 12345)

=========================================
LAST 10 ASX TRADE JOURNAL ENTRIES
=========================================
2026-02-18 10:03:15 | BUY   12 BHP.AX     @ $   42.00 | SUBMITTED  | Order: abc123...
```

**Key Indicators:**
- ✅ Timestamps at/after 10:00 AEST
- ✅ ASX tickers (*.AX)
- ✅ Order IDs present (not NULL)
- ✅ Status: SUBMITTED or FILLED

---

## Monitor Logs

### Real-time:
```bash
tail -f /Users/dynamiccode/clawd/quoterite/paper_trading/logs/runner_asx.log
```

### Expected Log Entries:

**Market Guard (at 10:00 AEST):**
```
2026-02-18 10:00:05 - INFO - Cycle 1: 2026-02-18 10:00:05
2026-02-18 10:00:05 - INFO - ASX Market status: OPEN
```

**Before 10:00 AEST:**
```
2026-02-18 09:55:00 - INFO - ASX Market status: CLOSED
2026-02-18 09:55:00 - INFO - ASX market closed - simulation paused
```

**Fallback Activation (Cycle 3):**
```
2026-02-18 10:02:00 - WARNING - No ASX signals (cycle 3)
2026-02-18 10:02:00 - INFO - 🔄 ASX FALLBACK ACTIVATED - Placing proof-of-life trade
2026-02-18 10:02:01 - INFO - 🇦🇺 ASX proof signal: BHP.AX x12 @ $42.00 = $504.00
2026-02-18 10:02:01 - INFO - 📝 Submitting ASX order: BUY 12 BHP.AX @ $42.00 LIMIT
2026-02-18 10:02:02 - INFO - ✅ ASX PROOF-OF-LIFE ORDER PLACED: BHP.AX x12 (Order ID: ...)
2026-02-18 10:02:02 - INFO - 📝 MVJ: BHP.AX x12 @ $42.00 (SUBMITTED)
```

---

## Stop ASX Trading

### Command:
```bash
kill $(cat /Users/dynamiccode/clawd/quoterite/paper_trading/logs/runner_asx.pid)
```

### Or:
```bash
cd /Users/dynamiccode/clawd/quoterite/paper_trading
pkill -F logs/runner_asx.pid
```

---

## ASX-Specific Constraints

### Minimum Marketable Parcel
- **Requirement:** First buy must be >= $500 AUD
- **Implementation:** Fallback strategy calculates minimum quantity
- **Example:** BHP @ $42 → need 12 shares ($504)

### Order Type
- **Type:** LIMIT orders only (not MARKET)
- **Reason:** Protects against bad fills if market data subscription missing
- **Price:** Uses conservative estimate from fallback strategy

### Tick Size Rounding
- **Status:** Not yet implemented (Error 110 protection)
- **TODO:** Add tick-size table for ASX securities
- **Priority:** Implement after first successful trade

### Dedupe
- **Implementation:** `fallback_activated` flag prevents multiple orders
- **Check:** Queries existing ASX positions before placing order
- **Result:** Only 1 ASX trade per session

---

## Files Created

### Core:
- `run_asx_trading.py` - ASX-specific runner
- `lib/fallback_asx.py` - ASX fallback strategy
- `start_asx_trading.sh` - Startup script
- `verify_asx_trades.sh` - Verification script

### Logs:
- `logs/runner_asx.log` - ASX runner log
- `logs/runner_asx.pid` - ASX runner PID

### Database:
- `trade_journal` table (with `limit_price` column)

---

## Troubleshooting

### ASX Runner Won't Start
```bash
# Check if already running
ps aux | grep run_asx_trading

# Check logs
tail -50 logs/runner_asx.log

# Verify env vars
echo $DATABASE_URL
echo $ALPHAVANTAGE_API_KEY
```

### No Trades Appearing
```bash
# Check market status (must be 10:00-16:00 AEST)
date

# Check fallback activation (after Cycle 3)
grep "FALLBACK ACTIVATED" logs/runner_asx.log

# Check wallet exists
psql "$DATABASE_URL" -c "SELECT name FROM wallets WHERE name NOT LIKE 'Test-Wallet-%' LIMIT 1"
```

### Order Rejected
```bash
# Check rejection reason in logs
grep "ORDER FAILED" logs/runner_asx.log

# Check wallet balance
psql "$DATABASE_URL" -c "SELECT name, current_balance, buying_power FROM wallets LIMIT 1"
```

---

## Timeline for Feb 18

**09:00 AEST** - US market closed, ASX pre-open  
**10:00 AEST** - ASX opens, runner activates  
**10:01 AEST** - Cycle 1 (no signals)  
**10:02 AEST** - Cycle 2 (no signals)  
**10:03 AEST** - Cycle 3 → **FALLBACK ACTIVATES**  
**10:04 AEST** - First ASX trade placed  
**10:05 AEST** - Verify via `verify_asx_trades.sh`  

---

## Next Steps After Proof-of-Life

1. ✅ Verify 1 successful ASX trade
2. ✅ Verify MVJ row with order_id + status
3. ⏳ Implement tick-size rounding (Error 110 protection)
4. ⏳ Add more ASX wallets (2-5)
5. ⏳ Implement Oracle signals for ASX
6. ⏳ Full ASX portfolio (10 wallets)

---

## Contact

Issues? Check logs first:
```bash
tail -100 logs/runner_asx.log
```

Then verify database:
```bash
bash verify_asx_trades.sh
```
