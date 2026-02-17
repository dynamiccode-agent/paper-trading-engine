# PRE-FLIGHT CHECKLIST - 23:30 AEST STARTUP

**Date:** 2026-02-17  
**Market:** NYSE/NASDAQ  
**Capital:** $100,000 (10 wallets × $10,000)  
**Auto-Start:** 23:30 AEST (US market open)

---

## ✅ COMPLETED

### 1. Wallets Created
- [x] 10 strategy wallets created
- [x] Each wallet: $10,000 initial balance
- [x] Total capital: $100,000
- [x] Different strategy names for tracking

**Wallet List:**
1. Momentum-Long - High momentum uptrend stocks
2. Value-Deep - Deep value undervalued stocks
3. Breakout-Tech - Tech sector breakout patterns
4. Mean-Reversion - Oversold bounce plays
5. Growth-Quality - High-quality growth stocks
6. Dividend-Yield - Dividend aristocrats
7. Small-Cap-Growth - Small cap growth momentum
8. Sector-Rotation - Sector rotation strategy
9. Volatility-Long - Long volatility plays
10. Options-Hedged - Options-hedged equity

### 2. Automated Startup Script
- [x] Created: `start_live_trading.sh`
- [x] Permissions: Executable
- [x] Logs directory: Created
- [x] Environment variables: Set

### 3. Cron Job Installed
- [x] Job ID: `b436cdf9-9550-420f-b506-f7c237ee6030`
- [x] Schedule: 23:30 AEST daily
- [x] Target: Main session
- [x] Wake mode: Now (immediate execution)
- [x] Next run: 2026-02-17 23:30:00 AEST

### 4. Backend Components
- [x] Paper trading engine: Tested
- [x] Strategy runner: Tested
- [x] Market data provider: Configured
- [x] Database: Connected (10 wallets ready)
- [x] API server: Ready (port 8000)

### 5. UI Components
- [x] Parallax UI: Built
- [x] SystemStatus panel: Integrated
- [x] Polling: Set to 20s
- [x] Dashboard: Functional
- [x] Wallet detail pages: Ready

### 6. Hardening Complete
- [x] Circuit breaker: Enabled (5-error threshold)
- [x] Market session guard: Active
- [x] Equity consistency checks: Enabled
- [x] Stale data detection: Active (>120s)
- [x] API key leakage: Audited (secure)
- [x] Detached runner: Tested (stable)

### 7. Monitoring Setup
- [x] Health endpoint: `/api/paper-trading/health`
- [x] Log files: `logs/runner.log`, `logs/api.log`
- [x] SystemStatus: Live in UI
- [x] Metrics tracking: Enabled

---

## 🎯 AUTO-START SEQUENCE (23:30 AEST)

**Cron will trigger:**
1. Stop any existing runners (cleanup)
2. Start API server (uvicorn on port 8000)
3. Start strategy runner (60s cycle)
4. Log startup event
5. Monitor logs automatically

**Expected behavior:**
```
23:30:00 - Cron triggers
23:30:02 - API server starts (PID logged)
23:30:05 - Strategy runner starts (PID logged)
23:30:06 - First cycle begins
23:31:00 - Market check (should be OPEN at US hours)
23:31:05 - Signals fetched from Oracle
23:31:10 - Orders submitted (if signals found)
23:31:15 - Trades executed
23:31:20 - Metrics snapshotted
```

---

## 📋 MANUAL STARTUP (IF NEEDED)

If cron fails or you want to start manually:

```bash
cd /Users/dynamiccode/clawd/quoterite/paper_trading
bash start_live_trading.sh
```

**Monitor:**
```bash
# Runner logs
tail -f logs/runner.log

# API logs
tail -f logs/api.log

# Check health
curl http://localhost:8000/api/paper-trading/health | jq
```

**Stop:**
```bash
kill $(cat logs/runner.pid)
kill $(cat logs/api.pid)
```

---

## 🔍 MONITORING PLAN (First 30 Min)

**Watch for:**
- ✅ Market status: OPEN (not CLOSED)
- ✅ Signals fetched: >0 signals
- ✅ Orders submitted: >0 orders
- ✅ Trades executed: Check fills
- ✅ Circuit breaker: OK (not OPEN)
- ✅ API health: <500ms latency
- ✅ Memory growth: <50MB in 30min

**Kill conditions:**
- ❌ Circuit breaker opens
- ❌ API latency >2000ms sustained
- ❌ DB connection errors
- ❌ Retry storms (exponential backoff spam)
- ❌ Memory growth >100MB in 30min

---

## 📊 SUCCESS METRICS (After 1 Hour)

**Validate:**
- [ ] All 10 wallets executed at least 1 cycle
- [ ] Trades logged in database
- [ ] Equity updated correctly
- [ ] Positions table populated
- [ ] UI reflects real data
- [ ] No errors in logs
- [ ] SystemStatus shows green

---

## 🚀 NEXT ACTIONS (Tonight)

**At 23:30:**
1. Cron will auto-start (no action needed)
2. Wait 5 minutes for first cycle
3. Check logs: `tail -f logs/runner.log`
4. Open Parallax UI: View dashboard

**At 23:35 (first cycle complete):**
1. Verify trades executed
2. Check equity changes
3. Confirm SystemStatus green
4. Report to Tyler:
   - First trade log entry
   - Equity before/after
   - SystemStatus panel state

**At 00:00 (30 min in):**
1. Check for any warnings
2. Verify stable performance
3. Confirm no memory leaks
4. All wallets cycling correctly

---

## 📝 NOTES

**Tyler's directive:**
- Start at 23:30 (US market open)
- 10 wallets ($10K each)
- Different strategies per wallet
- Learn at scale
- NYSE/NASDAQ only

**Constraints:**
- This is a validation test
- First overnight run
- Close monitoring required
- Can scale to 20/50 wallets after success

**Environment:**
- Database: Neon Postgres (Sydney)
- API: FastAPI on port 8000
- Runner: 60s cycle interval
- Market data: AlphaVantage (cached)

---

## ✅ READY TO GO

All systems green. Cron job active. Will auto-start at 23:30 AEST.

**Next update:** First cycle results (23:35 AEST)
