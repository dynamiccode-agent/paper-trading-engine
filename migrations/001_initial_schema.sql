-- Migration 001: Initial Paper Trading Schema
-- Created: 2026-02-17
-- Description: Core tables for paper trading engine

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- ENUMS
-- ============================================================================

CREATE TYPE order_side AS ENUM ('BUY', 'SELL');
CREATE TYPE order_type AS ENUM ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT');
CREATE TYPE order_status AS ENUM (
    'PENDING',      -- Created, not yet submitted
    'SUBMITTED',    -- Submitted to execution engine
    'PARTIAL',      -- Partially filled
    'FILLED',       -- Completely filled
    'CANCELLED',    -- Cancelled by user/system
    'REJECTED'      -- Rejected by engine
);

CREATE TYPE market_type AS ENUM ('ASX', 'NASDAQ', 'NYSE', 'TSX');

-- ============================================================================
-- WALLETS
-- ============================================================================

CREATE TABLE wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    capital_tier TEXT NOT NULL,  -- '1k', '10k', '20k', '40k', '50k'
    initial_balance DECIMAL(15,2) NOT NULL CHECK (initial_balance > 0),
    current_balance DECIMAL(15,2) NOT NULL CHECK (current_balance >= 0),
    reserved_balance DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (reserved_balance >= 0),
    buying_power DECIMAL(15,2) GENERATED ALWAYS AS (current_balance - reserved_balance) STORED,
    strategy_id UUID,  -- FK to strategies table (future)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_balance CHECK (current_balance + reserved_balance <= initial_balance * 2)  -- Max 2x initial (prevents drift)
);

CREATE INDEX idx_wallets_tier ON wallets(capital_tier);
CREATE INDEX idx_wallets_strategy ON wallets(strategy_id);

COMMENT ON TABLE wallets IS 'Paper trading wallets with capital allocation tracking';
COMMENT ON COLUMN wallets.reserved_balance IS 'Capital reserved for open orders (locks buying power)';
COMMENT ON COLUMN wallets.buying_power IS 'Available capital for new orders (computed)';

-- ============================================================================
-- ORDERS
-- ============================================================================

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    market market_type NOT NULL,
    side order_side NOT NULL,
    order_type order_type NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    filled_quantity INTEGER NOT NULL DEFAULT 0 CHECK (filled_quantity >= 0 AND filled_quantity <= quantity),
    limit_price DECIMAL(15,4),  -- Required for LIMIT orders
    stop_price DECIMAL(15,4),   -- Required for STOP orders
    avg_fill_price DECIMAL(15,4),  -- Computed from fills
    status order_status NOT NULL DEFAULT 'PENDING',
    rejection_reason TEXT,
    oracle_signal JSONB,  -- Store original signal that triggered order
    submitted_at TIMESTAMP,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT limit_price_required CHECK (
        (order_type IN ('LIMIT', 'STOP_LIMIT') AND limit_price IS NOT NULL) 
        OR (order_type NOT IN ('LIMIT', 'STOP_LIMIT'))
    ),
    CONSTRAINT stop_price_required CHECK (
        (order_type IN ('STOP', 'STOP_LIMIT') AND stop_price IS NOT NULL)
        OR (order_type NOT IN ('STOP', 'STOP_LIMIT'))
    ),
    CONSTRAINT filled_qty_status CHECK (
        (status = 'FILLED' AND filled_quantity = quantity)
        OR (status = 'PARTIAL' AND filled_quantity > 0 AND filled_quantity < quantity)
        OR (status IN ('PENDING', 'SUBMITTED', 'CANCELLED', 'REJECTED') AND filled_quantity = 0)
    ),
    CONSTRAINT rejection_reason_required CHECK (
        (status = 'REJECTED' AND rejection_reason IS NOT NULL)
        OR (status != 'REJECTED')
    )
);

CREATE INDEX idx_orders_wallet ON orders(wallet_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_ticker ON orders(ticker, market);
CREATE INDEX idx_orders_created ON orders(created_at DESC);

COMMENT ON TABLE orders IS 'Order intent tracking with fill status';
COMMENT ON COLUMN orders.filled_quantity IS 'Accumulated filled quantity (supports partial fills)';
COMMENT ON COLUMN orders.avg_fill_price IS 'Volume-weighted average fill price across all fills';

-- ============================================================================
-- TRADES (Immutable Ledger)
-- ============================================================================

CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
    ticker TEXT NOT NULL,
    market market_type NOT NULL,
    side order_side NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    fill_price DECIMAL(15,4) NOT NULL CHECK (fill_price > 0),
    slippage_bps DECIMAL(8,4),  -- Basis points (0.01% = 1 bps)
    commission DECIMAL(10,4) NOT NULL DEFAULT 0,
    gross_amount DECIMAL(15,2) NOT NULL,  -- quantity × fill_price
    net_amount DECIMAL(15,2) NOT NULL,    -- gross_amount + commission (BUY: positive, SELL: negative)
    quote_bid DECIMAL(15,4),  -- Market bid at fill time
    quote_ask DECIMAL(15,4),  -- Market ask at fill time
    quote_mid DECIMAL(15,4),  -- Market mid at fill time
    filled_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_gross_amount CHECK (gross_amount = quantity * fill_price),
    CONSTRAINT valid_net_amount CHECK (
        (side = 'BUY' AND net_amount >= gross_amount)
        OR (side = 'SELL' AND net_amount <= gross_amount)
    )
);

CREATE INDEX idx_trades_order ON trades(order_id);
CREATE INDEX idx_trades_wallet ON trades(wallet_id);
CREATE INDEX idx_trades_ticker ON trades(ticker, market);
CREATE INDEX idx_trades_filled ON trades(filled_at DESC);

COMMENT ON TABLE trades IS 'Immutable append-only trade ledger (fills)';
COMMENT ON COLUMN trades.slippage_bps IS 'Execution slippage in basis points from mid-quote';
COMMENT ON COLUMN trades.net_amount IS 'Final cash impact including commission';

-- ============================================================================
-- POSITIONS
-- ============================================================================

CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    market market_type NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity != 0),  -- Allow negative (short positions future)
    avg_entry_price DECIMAL(15,4) NOT NULL CHECK (avg_entry_price > 0),
    total_cost DECIMAL(15,2) NOT NULL,  -- Sum of (quantity × entry_price) + commissions
    realised_pnl DECIMAL(15,2) NOT NULL DEFAULT 0,  -- Locked-in PnL from closed portions
    opened_at TIMESTAMP NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(wallet_id, ticker, market),  -- One position per ticker per wallet
    CONSTRAINT position_closed CHECK (
        (quantity = 0 AND closed_at IS NOT NULL)
        OR (quantity != 0 AND closed_at IS NULL)
    )
);

CREATE INDEX idx_positions_wallet ON positions(wallet_id);
CREATE INDEX idx_positions_ticker ON positions(ticker, market);
CREATE INDEX idx_positions_open ON positions(wallet_id) WHERE closed_at IS NULL;

COMMENT ON TABLE positions IS 'Current position tracking (quantity + cost basis only)';
COMMENT ON COLUMN positions.avg_entry_price IS 'Volume-weighted average entry price';
COMMENT ON COLUMN positions.realised_pnl IS 'Locked-in PnL from partial closes';
COMMENT ON COLUMN positions.quantity IS 'Current shares held (0 = closed position)';

-- NOTE: current_price and unrealised_pnl are NOT STORED
-- They must be computed at query time from latest market_data

-- ============================================================================
-- MARKET DATA CACHE
-- ============================================================================

CREATE TABLE market_data (
    ticker TEXT NOT NULL,
    market market_type NOT NULL,
    price DECIMAL(15,4) NOT NULL CHECK (price > 0),
    bid DECIMAL(15,4) CHECK (bid > 0),
    ask DECIMAL(15,4) CHECK (ask > 0),
    volume BIGINT CHECK (volume >= 0),
    provider TEXT NOT NULL,  -- 'alphavantage', 'yahoo', etc.
    timestamp TIMESTAMP NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (ticker, market, timestamp),
    CONSTRAINT valid_spread CHECK (ask IS NULL OR bid IS NULL OR ask >= bid)
);

CREATE INDEX idx_market_data_latest ON market_data(ticker, market, timestamp DESC);
CREATE INDEX idx_market_data_fetched ON market_data(fetched_at DESC);

COMMENT ON TABLE market_data IS 'Market quote cache (time-series)';
COMMENT ON COLUMN market_data.timestamp IS 'Quote timestamp from provider';
COMMENT ON COLUMN market_data.fetched_at IS 'When we fetched it';

-- ============================================================================
-- STRATEGY METRICS
-- ============================================================================

CREATE TABLE strategy_metrics (
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    equity DECIMAL(15,2) NOT NULL,  -- Snapshot: balance + position values
    pnl DECIMAL(15,2) NOT NULL,
    pnl_pct DECIMAL(8,4) NOT NULL,
    win_rate DECIMAL(5,4),  -- 0.0 to 1.0
    sharpe_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    trade_count INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (wallet_id, date)
);

CREATE INDEX idx_metrics_wallet ON strategy_metrics(wallet_id, date DESC);
CREATE INDEX idx_metrics_date ON strategy_metrics(date DESC);

COMMENT ON TABLE strategy_metrics IS 'Daily strategy performance snapshots';

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER wallets_updated_at BEFORE UPDATE ON wallets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER positions_updated_at BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- VIEWS (Helper queries)
-- ============================================================================

-- View: Current positions with unrealised PnL
CREATE OR REPLACE VIEW positions_current AS
SELECT 
    p.id,
    p.wallet_id,
    p.ticker,
    p.market,
    p.quantity,
    p.avg_entry_price,
    p.total_cost,
    p.realised_pnl,
    md.price AS current_price,
    md.timestamp AS price_timestamp,
    (md.price * p.quantity) AS current_value,
    ((md.price * p.quantity) - p.total_cost) AS unrealised_pnl,
    ((md.price * p.quantity) - p.total_cost) / NULLIF(p.total_cost, 0) * 100 AS unrealised_pnl_pct,
    p.opened_at,
    p.updated_at
FROM positions p
LEFT JOIN LATERAL (
    SELECT price, timestamp
    FROM market_data
    WHERE ticker = p.ticker AND market = p.market
    ORDER BY timestamp DESC
    LIMIT 1
) md ON true
WHERE p.closed_at IS NULL;

COMMENT ON VIEW positions_current IS 'Open positions with computed unrealised PnL from latest quotes';

-- View: Wallet equity (balance + position values)
CREATE OR REPLACE VIEW wallets_equity AS
SELECT 
    w.id,
    w.name,
    w.capital_tier,
    w.initial_balance,
    w.current_balance,
    w.reserved_balance,
    w.buying_power,
    COALESCE(SUM(pc.current_value), 0) AS position_value,
    w.current_balance + COALESCE(SUM(pc.current_value), 0) AS total_equity,
    (w.current_balance + COALESCE(SUM(pc.current_value), 0) - w.initial_balance) AS total_pnl,
    ((w.current_balance + COALESCE(SUM(pc.current_value), 0) - w.initial_balance) / w.initial_balance * 100) AS total_pnl_pct
FROM wallets w
LEFT JOIN positions_current pc ON pc.wallet_id = w.id
GROUP BY w.id;

COMMENT ON VIEW wallets_equity IS 'Wallet equity = balance + open position values';

-- ============================================================================
-- SAMPLE DATA (Testing only - remove in production)
-- ============================================================================

-- INSERT INTO wallets (name, capital_tier, initial_balance, current_balance) VALUES
-- ('Wallet-1K-01', '1k', 1000.00, 1000.00),
-- ('Wallet-10K-01', '10k', 10000.00, 10000.00),
-- ('Wallet-50K-01', '50k', 50000.00, 50000.00);
