-- Migration 004: Trade Journal (Minimal Viable Journal for proof-of-life)
-- Created: 2026-02-18

CREATE TABLE IF NOT EXISTS trade_journal (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL,
    limit_price DECIMAL(15,4),  -- For LIMIT orders (ASX requires this)
    order_id UUID,  -- NULL if order failed before submission
    status TEXT NOT NULL,  -- SUBMITTED | FILLED | FAILED
    reason TEXT NOT NULL,  -- Why this trade was placed
    outcome TEXT,  -- Final outcome (filled, rejected, etc.)
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trade_journal_wallet ON trade_journal(wallet_id);
CREATE INDEX idx_trade_journal_created ON trade_journal(created_at DESC);
CREATE INDEX idx_trade_journal_ticker ON trade_journal(ticker);

COMMENT ON TABLE trade_journal IS 'Minimal viable journal for trade decisions and outcomes';
COMMENT ON COLUMN trade_journal.reason IS 'Why the trade was placed (strategy signal, fallback, etc.)';
COMMENT ON COLUMN trade_journal.outcome IS 'Final outcome after execution';
