-- Migration 005: Trade Intelligence Layer
-- Adds decision tracking, learning capture, and strategy configuration

-- Trade Decision Intelligence
CREATE TABLE IF NOT EXISTS trade_decisions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  trade_id UUID REFERENCES trades(id) ON DELETE CASCADE,
  wallet_id UUID REFERENCES wallets(id) ON DELETE CASCADE,
  
  -- Signal Context
  signal_source TEXT NOT NULL, -- 'oracle' | 'fallback' | 'manual'
  signal_score DECIMAL(5,2),
  trigger_condition TEXT,
  
  -- Market Context
  market_regime TEXT, -- 'trending' | 'consolidating' | 'volatile'
  trend_direction TEXT, -- 'up' | 'down' | 'sideways'
  volume_context TEXT, -- 'high' | 'normal' | 'low'
  macro_condition TEXT,
  
  -- Entry Reasoning
  entry_thesis TEXT NOT NULL,
  supporting_factors JSONB,
  risk_assumption TEXT,
  expected_move JSONB, -- {target_pct, stop_pct, timeframe}
  
  -- Technical Context
  technical_indicators JSONB,
  
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_decisions_trade_id ON trade_decisions(trade_id);
CREATE INDEX IF NOT EXISTS idx_trade_decisions_wallet_id ON trade_decisions(wallet_id);

-- Trade Learnings
CREATE TABLE IF NOT EXISTS trade_learnings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  trade_id UUID REFERENCES trades(id) ON DELETE CASCADE,
  wallet_id UUID REFERENCES wallets(id) ON DELETE CASCADE,
  
  learning_type TEXT, -- 'success_pattern' | 'failure_pattern' | 'timing' | 'sizing'
  key_takeaway TEXT NOT NULL,
  context_tags TEXT[], -- ['breakout', 'low_volume', 'macro_headwind']
  confidence INTEGER CHECK (confidence >= 1 AND confidence <= 10),
  
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_learnings_trade_id ON trade_learnings(trade_id);
CREATE INDEX IF NOT EXISTS idx_trade_learnings_wallet_id ON trade_learnings(wallet_id);

-- Daily Wallet Logs
CREATE TABLE IF NOT EXISTS daily_wallet_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  wallet_id UUID REFERENCES wallets(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  
  -- Daily Performance
  trades_executed INTEGER DEFAULT 0,
  positions_opened INTEGER DEFAULT 0,
  positions_closed INTEGER DEFAULT 0,
  win_count INTEGER DEFAULT 0,
  loss_count INTEGER DEFAULT 0,
  daily_pnl DECIMAL(15,2) DEFAULT 0,
  
  -- Daily Summary
  performance_summary TEXT,
  key_events TEXT[],
  market_conditions TEXT,
  
  -- Strategy State
  strategy_adjustments JSONB,
  
  UNIQUE(wallet_id, date),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_wallet_logs_wallet_date ON daily_wallet_logs(wallet_id, date DESC);

-- Wallet Learning Summary (Rolling)
CREATE TABLE IF NOT EXISTS wallet_learning_summary (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  wallet_id UUID REFERENCES wallets(id) ON DELETE CASCADE UNIQUE,
  
  -- Pattern Recognition
  most_common_mistake TEXT,
  most_successful_pattern TEXT,
  win_rate_by_regime JSONB, -- {trending: 0.65, consolidating: 0.45}
  
  -- Performance Metrics
  avg_hold_time_hours DECIMAL(10,2),
  best_time_of_day TEXT,
  worst_time_of_day TEXT,
  
  -- Next Adjustments
  planned_adjustments JSONB,
  
  last_updated TIMESTAMP DEFAULT NOW()
);

-- Add strategy configuration to wallets
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS strategy_type TEXT DEFAULT 'multi_position';
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS max_positions INTEGER DEFAULT 5;
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS rebalance_frequency TEXT DEFAULT 'daily';

-- Update existing wallets with strategy types
UPDATE wallets SET strategy_type = 'multi_position', max_positions = 5 WHERE name = 'Momentum-Long';
UPDATE wallets SET strategy_type = 'portfolio', max_positions = 10 WHERE name = 'Value-Deep';
UPDATE wallets SET strategy_type = 'multi_position', max_positions = 3 WHERE name = 'Breakout-Tech';
UPDATE wallets SET strategy_type = 'multi_position', max_positions = 5 WHERE name = 'Mean-Reversion';
UPDATE wallets SET strategy_type = 'portfolio', max_positions = 8 WHERE name = 'Growth-Quality';
UPDATE wallets SET strategy_type = 'portfolio', max_positions = 12 WHERE name = 'Dividend-Yield';
UPDATE wallets SET strategy_type = 'multi_position', max_positions = 7 WHERE name = 'Small-Cap-Growth';
UPDATE wallets SET strategy_type = 'portfolio', max_positions = 10 WHERE name = 'Sector-Rotation';
UPDATE wallets SET strategy_type = 'single_position', max_positions = 1 WHERE name = 'Volatility-Long';
UPDATE wallets SET strategy_type = 'multi_position', max_positions = 5 WHERE name = 'Options-Hedged';

COMMENT ON TABLE trade_decisions IS 'Captures the reasoning, context, and expectations for each trade decision';
COMMENT ON TABLE trade_learnings IS 'Stores key learnings extracted from trade outcomes';
COMMENT ON TABLE daily_wallet_logs IS 'Daily performance summaries and strategy state for each wallet';
COMMENT ON TABLE wallet_learning_summary IS 'Rolling summary of patterns and planned adjustments per wallet';
