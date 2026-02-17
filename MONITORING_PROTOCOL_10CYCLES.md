# MONITORING PROTOCOL - 10 CYCLES

**Based on Tyler's directive (21:36 AEST)**

---

## 🎯 NEXT 30 MINUTES - CRITICAL CHECKS

### 1. Accounting Sanity Check (EVERY CYCLE)

**For each wallet that traded:**

```
Wallet: Momentum-Long
  cash_balance: $8,245.50
  position_value: $1,752.35 (qty × latest mid)
  equity: $9,997.85
  equity_diff: $0.00 ✅
```

**Rule:** If `equity_diff > $0.01` → **INVESTIGATE IMMEDIATELY**

**Equity formula:**
```
equity = cash_balance + position_value
equity_diff = abs(equity - (cash_balance + computed_position_value))
```

**Tolerance:** ≤ $0.01 (unless intentional rounding)

---

### 2. Fill Realism Check (EVERY FILL)

**For each trade fill, log:**

```
Trade: BUY 10 AAPL
  ticker: AAPL
  side: BUY
  qty: 10
  bid/ask at fill: $175.45 / $175.55 (mid: $175.50)
  fill_price: $175.52
  slippage: +$0.02 (+1.14 bps)
  commission: $1.00
```

**Rule of thumb:**
- BUY fills should **not routinely be below bid/ask mid** unless model allows it
- Reasonable slippage: 5-20 bps for liquid stocks
- Commission: $1.00 flat per trade

**Red flags:**
- Fill price below bid (for BUY)
- Fill price above ask (for SELL)
- Slippage >50 bps on liquid stocks

---

### 3. Cache Freshness

**Monitor:**
```
Market Data: Fresh (45s) ✅
```

**Thresholds:**
- <60s: ✅ Fresh
- 60-120s: ⚠️ Warning
- >120s: 🚨 **PAUSE TRADING**

**Action:** If cache goes stale (>120s), runner should skip cycle until fresh.

---

### 4. API Usage (AlphaVantage)

**Track separately:**
- AlphaVantage API calls/min (external)
- Local FastAPI calls/min (internal)

**Expected with 5 wallets:**
- Single-digit to low teens per minute
- NOT >30/min

**If >30/min → something's wrong (likely cache not working)**

**Current status:**
```
AlphaVantage calls/min: 8 ✅
Local API calls/min: 24 (UI polling)
```

---

### 5. Kill Conditions (UNCHANGED)

**Immediate shutdown if:**
- ❌ Circuit breaker OPEN
- ❌ DB connection errors
- ❌ Retry storms (exponential backoff spam)
- ❌ Memory blowup (>100MB growth in 30min)
- ❌ API latency >2000ms average sustained

---

## 📊 10-CYCLE REPORT (COMPACT)

**After 10 cycles, report:**

```
10-CYCLE SUMMARY
================

Execution:
- Cycles completed: 10/10 ✅
- Cycles missed: 0

Trades:
- Submitted: 42
- Filled: 40
- Rejected: 2

Top 3 Rejection Reasons:
1. Insufficient buying power (1 occurrence)
2. Signal score too low (1 occurrence)

Accounting:
- Worst equity_diff observed: $0.00 ✅

Performance:
- AlphaVantage calls/min peak: 12 ✅
- Average cycle time: 15.3s
- Memory growth: +3.2 MB

Errors:
- Circuit breaker events: 0 ✅
- DB errors: 0 ✅
- Retry storms: 0 ✅

Overnight Page:
- [Screenshot or summary once populated]
```

---

## 📋 CYCLE-BY-CYCLE LOG FORMAT

**Example log entry:**

```
=============================================================
Cycle 3: 2026-02-17 23:33:05
=============================================================

Market: OPEN ✅
Wallets processed: 5

--- Momentum-Long ---
Signals fetched: 2
Orders submitted: 2 (BUY AAPL, BUY MSFT)

Trade 1: BUY 10 AAPL @ $175.52
  Bid/Ask: $175.45 / $175.55 (mid: $175.50)
  Slippage: +$0.02 (+1.14 bps) ✅
  Commission: $1.00
  
Trade 2: BUY 5 MSFT @ $420.10
  Bid/Ask: $420.00 / $420.20 (mid: $420.10)
  Slippage: $0.00 (0 bps) ✅
  Commission: $1.00

Accounting Check:
  Cash balance: $8,243.90
  Position value: $1,753.95 (15 shares)
  Equity: $9,997.85
  Equity diff: $0.00 ✅

--- Value-Deep ---
No signals above threshold (min_score=70)
Orders: 0

--- Breakout-Tech ---
[... similar format for other wallets]

Cache Status: Fresh (42s) ✅
AlphaVantage calls this cycle: 4
Total calls/min: 8 ✅

Cycle complete in 15.2s
```

---

## 🚨 INVESTIGATION TRIGGERS

**If any of these occur, investigate immediately:**

1. **equity_diff > $0.01**
   - Log wallet details
   - Check position calculations
   - Verify market data freshness
   - Review trade ledger

2. **Fill price anomaly**
   - BUY below bid
   - SELL above ask
   - Slippage >50 bps on liquid stock

3. **AlphaVantage calls >30/min**
   - Check cache hit rate
   - Verify cache TTL (should be 60s)
   - Look for redundant fetches

4. **Cache stale >120s**
   - Pause trading immediately
   - Check AlphaVantage rate limits
   - Verify circuit breaker not stuck

5. **Memory growth >50MB in 30min**
   - Check for memory leaks
   - Verify object cleanup
   - Review cache size

---

## 📸 OVERNIGHT PAGE CONTENT

**Once populated, capture:**
- Headline: "While You Slept" summary
- PnL change per wallet
- Top 5 winners/losers
- Notable trades
- Narrative summary

**Format:**
```
Overnight Summary (2026-02-17 to 2026-02-18)
============================================

While You Slept:
$100,000 → $99,985.40 (-$14.60, -0.015%)

Top Performers:
1. Breakout-Tech: +$45.20 (+0.45%)
2. Growth-Quality: +$32.10 (+0.32%)
3. Momentum-Long: +$18.50 (+0.19%)

Bottom Performers:
1. Value-Deep: -$62.30 (-0.62%)
2. Volatility-Long: -$28.40 (-0.28%)
3. Mean-Reversion: -$19.70 (-0.20%)

Notable Trades:
- Breakout-Tech: BUY 20 NVDA @ $850.25 (+$45.20)
- Value-Deep: SELL 15 XOM @ $108.50 (-$62.30)

[Screenshot of UI attached]
```

---

## ✅ TYLER'S NOTE ACKNOWLEDGED

**"Equity dropping right after a BUY is normal if you model spread + slippage + commission."**

**Confirmed:** Our simulator includes:
- Bid/ask spread (10 bps modeled)
- Slippage (5-20 bps realistic)
- Commission ($1.00 per trade)

**Expected behavior:**
- Equity dip immediately after BUY = correct modeling
- Not "free money" = good sign ✅

---

## 🎯 NEXT MILESTONE

**After 10 cycles:**
- Paste compact report to Tyler
- Tyler decides: 5 wallets → 10 wallets (or tighten one piece)
- Typical fixes: caching or fill math

---

**Built:** 2026-02-17 21:41 AEST  
**By:** Atlas (Tyler's monitoring spec)
