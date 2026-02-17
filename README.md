# Paper Trading Engine

**Production-grade paper trading simulator for Parallax**

Built to validate trading strategies at scale without broker constraints.

---

## Architecture

### Database Layer
- **Wallets**: Capital allocation, buying power, reservations
- **Orders**: Order intent tracking with fill status
- **Trades**: Immutable append-only ledger (all fills)
- **Positions**: Quantity + cost basis only (NO stored prices)
- **Market Data**: Cached quotes with pluggable providers

### Execution Engine
1. `submit_order(wallet_id, OrderIntent)` → creates Order (SUBMITTED)
2. `match_and_fill(order_id, Quote)` → creates Trade fills
3. `apply_fill_to_wallet_and_position()` → updates atomically
4. Rejection paths return explicit reason codes

### Design Principles
1. **No stored prices in positions** — computed from latest market data
2. **Immutable trade ledger** — append-only, auditable
3. **Atomic wallet updates** — balance + positions updated together
4. **Pluggable market data** — provider abstraction layer
5. **Realistic fills** — slippage + commission + spread modeling

---

## Database Schema

### Wallets
```sql
id UUID PRIMARY KEY
name TEXT
capital_tier TEXT  -- '1k', '10k', '20k', '40k', '50k'
initial_balance DECIMAL(15,2)
current_balance DECIMAL(15,2)
reserved_balance DECIMAL(15,2)  -- Locks buying power for open orders
buying_power GENERATED (current_balance - reserved_balance)
```

### Orders
```sql
id UUID PRIMARY KEY
wallet_id UUID REFERENCES wallets
ticker TEXT
market ENUM('ASX', 'NASDAQ', 'NYSE', 'TSX')
side ENUM('BUY', 'SELL')
order_type ENUM('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT')
quantity INTEGER
filled_quantity INTEGER  -- Supports partial fills
limit_price DECIMAL(15,4)  -- For LIMIT orders
stop_price DECIMAL(15,4)   -- For STOP orders
avg_fill_price DECIMAL(15,4)  -- Volume-weighted average
status ENUM('PENDING', 'SUBMITTED', 'PARTIAL', 'FILLED', 'CANCELLED', 'REJECTED')
rejection_reason TEXT
oracle_signal JSONB  -- Original signal that triggered order
```

### Trades (Immutable)
```sql
id UUID PRIMARY KEY
order_id UUID REFERENCES orders
wallet_id UUID REFERENCES wallets
ticker TEXT
market ENUM
side ENUM
quantity INTEGER
fill_price DECIMAL(15,4)
slippage_bps DECIMAL(8,4)  -- Execution slippage in basis points
commission DECIMAL(10,4)
gross_amount DECIMAL(15,2)  -- quantity × fill_price
net_amount DECIMAL(15,2)    -- gross_amount ± commission
quote_bid DECIMAL(15,4)     -- Market state at fill time
quote_ask DECIMAL(15,4)
quote_mid DECIMAL(15,4)
filled_at TIMESTAMP
```

### Positions
```sql
id UUID PRIMARY KEY
wallet_id UUID REFERENCES wallets
ticker TEXT
market ENUM
quantity INTEGER  -- Can be 0 when closed
avg_entry_price DECIMAL(15,4)
total_cost DECIMAL(15,2)
realised_pnl DECIMAL(15,2)  -- Locked-in PnL from partial closes
opened_at TIMESTAMP
closed_at TIMESTAMP

-- NOTE: current_price and unrealised_pnl are COMPUTED (not stored)
```

---

## Order Flow

### 1. Submit Order
```python
intent = OrderIntent(
    wallet_id=wallet_id,
    ticker='AAPL',
    market=Market.NASDAQ,
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=10
)

order, rejection = engine.submit_order(intent)
```

**Validation:**
- Wallet exists and has sufficient buying power
- Market data available
- Order parameters valid

**For BUY orders:**
- Reserves capital: `estimated_amount + commission`
- Locks buying power until fill/cancel

### 2. Match & Fill
```python
filled = engine.match_and_fill(order_id)
```

**Fill Logic:**
- **MARKET orders**: Fill at bid (SELL) or ask (BUY) with slippage
- **LIMIT orders**: Fill only if limit price breached
- **Partial fills**: Supported (future: liquidity constraints)

**Slippage Model:**
- Random within spread (±spread/2)
- Configurable via `enable_slippage` flag

### 3. Apply Fill
**BUY:**
1. Deduct `net_amount` from wallet balance
2. Release reserved capital
3. Create/update position (average up if adding)

**SELL:**
1. Add `net_amount` to wallet balance
2. Reduce position quantity
3. Calculate realised PnL: `proceeds - cost_basis_sold - commission`

---

## Market Data Providers

### AlphaVantageProvider
- Free tier: 25 req/day, 5 req/min
- Requires API key
- Spread modeled via configurable `spread_bps`

```python
provider = AlphaVantageProvider(
    api_key='YOUR_KEY',
    cache_ttl=60,  # seconds
    spread_bps=Decimal('10')  # 10 bps = 0.1%
)
```

### MockMarketDataProvider (Testing)
- No API required
- Realistic fake data
- Instant quotes

```python
provider = MockMarketDataProvider(
    spread_bps=Decimal('10')
)
```

### Future: YahooFinanceProvider
- Free, no key required
- Real bid/ask spreads
- High rate limits

---

## Usage

### Setup
```bash
cd paper_trading

# Install dependencies
pip install -r requirements.txt

# Set database URL
export DATABASE_URL="postgresql://..."

# Apply migrations
python apply_migration.py 001
```

### Run Test
```bash
python test_engine.py
```

**Expected Output:**
```
✅ Created wallet: 10K
✅ BUY 10 AAPL @ $180.55 (filled)
✅ Position opened (10 shares)
✅ SELL 5 AAPL @ $180.44 (filled)
✅ Position reduced (5 shares)
✅ Realised PnL: -$1.55
✅ Unrealised PnL: -$1.27
✅ Equity: $9,997.18
```

---

## Key Features

### ✅ Implemented
- [x] Wallet management (balance, buying power, reservations)
- [x] Order submission with validation
- [x] Market order fills with slippage
- [x] Position tracking (quantity + cost basis)
- [x] Immutable trade ledger
- [x] Realised vs unrealised PnL
- [x] Commission support
- [x] Market data caching
- [x] Pluggable providers
- [x] Test CLI

### 🚧 Next Phase
- [ ] Limit order matching
- [ ] Stop orders
- [ ] Partial fills (liquidity constraints)
- [ ] Strategy runner (Oracle integration)
- [ ] Batch wallet creation (10× 1k, 10× 10k, etc.)
- [ ] Daily metrics snapshots
- [ ] UI dashboard
- [ ] Analytics + probability scoring

---

## Files

```
paper_trading/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── apply_migration.py          # Migration runner
├── test_engine.py              # Test CLI
├── migrations/
│   ├── 001_initial_schema.sql        # Core tables + views
│   ├── 001_initial_schema_down.sql   # Rollback
│   └── 002_fix_trade_constraints.sql # Decimal precision fix
└── lib/
    ├── __init__.py
    ├── types.py                # Data classes
    ├── engine.py               # Core execution engine
    ├── market_data.py          # Provider abstraction
    └── mock_market_data.py     # Testing provider
```

---

## Testing

### Manual Test
```bash
python test_engine.py
```

### Unit Tests (Future)
```bash
pytest tests/
```

---

## Performance

**Targets (Phase 2):**
- 50 wallets × 5 orders/day = 250 orders/day
- Sub-second order submission
- Sub-100ms fill execution
- Daily metrics computed in <1s

---

## Why This Approach?

**vs IBKR Paper Trading:**
- ❌ IBKR: $1k-$10k balance limits, margin requirements, API friction
- ✅ Ours: Unlimited wallets, configurable capital, full control

**vs Toy Simulators:**
- ❌ Toys: Fake math, no ledger, drift in equity
- ✅ Ours: Production-grade accounting, immutable ledger, realistic fills

**vs Live Trading:**
- ❌ Live: Risk capital, broker constraints, slow validation
- ✅ Ours: Zero risk, instant testing, statistical validation at scale

---

## Next Steps

1. **Strategy Integration** → Connect Oracle signals to order intents
2. **Batch Wallets** → Generate 50 wallets (10× each tier)
3. **Daily Runner** → Cron job to execute strategies
4. **Analytics** → Aggregate performance across wallets
5. **UI Dashboard** → Visualize equity curves, trades, positions
6. **Probability Scoring** → Identify high-confidence patterns

---

## Architecture Decisions (Tyler's Fixes Applied)

### 1. Positions: No Stored Prices
**Problem:** Storing `current_price` and `unrealised_pnl` causes drift
**Solution:** Store ONLY: `quantity`, `avg_entry_price`, `total_cost`, `realised_pnl`
**Compute:** Unrealised PnL = `(current_market_price × qty) - total_cost`

### 2. Trades: Full Status Tracking
**Problem:** Need to handle partial fills and rejections
**Solution:** 
- `filled_quantity` (supports partial)
- `avg_fill_price` (volume-weighted)
- `status` enum (PENDING → SUBMITTED → PARTIAL → FILLED)
- `rejection_reason` for failures

### 3. Spread Model: Configurable
**Problem:** Hardcoding `price ± 0.01%` unrealistic
**Solution:**
- Provider abstraction with `get_spread_model()`
- Alpha Vantage: configurable `spread_bps` parameter
- Future: Real bid/ask from provider

---

## Contributing

When extending:
1. **Database changes** → Create migration file
2. **New providers** → Implement `MarketDataProvider` interface
3. **New order types** → Extend `_calculate_fill_price()`
4. **Tests** → Add to `tests/` directory

---

## License

Internal Dynamic Code project.

---

**Status:** ✅ Foundation complete  
**Next:** Strategy integration + batch wallets + UI  
**Built:** 2026-02-17  
**By:** Atlas (via Tyler's spec)
