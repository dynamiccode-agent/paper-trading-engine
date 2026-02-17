-- Migration 003: Strategy Metrics Rollup View
-- Created: 2026-02-17
-- Description: Aggregated daily metrics by capital tier for Phase 3

-- ============================================================================
-- STRATEGY METRICS ROLLUP (Daily by Tier)
-- ============================================================================

CREATE OR REPLACE VIEW strategy_metrics_rollup_daily AS
SELECT 
    sm.date,
    w.capital_tier,
    COUNT(DISTINCT w.id) AS wallet_count,
    
    -- Equity stats
    AVG(sm.equity) AS avg_equity,
    MIN(sm.equity) AS min_equity,
    MAX(sm.equity) AS max_equity,
    STDDEV(sm.equity) AS stddev_equity,
    
    -- PnL stats
    SUM(sm.pnl) AS total_pnl,
    AVG(sm.pnl) AS avg_pnl,
    AVG(sm.pnl_pct) AS avg_pnl_pct,
    MIN(sm.pnl_pct) AS min_pnl_pct,
    MAX(sm.pnl_pct) AS max_pnl_pct,
    
    -- Performance stats
    AVG(sm.win_rate) AS avg_win_rate,
    AVG(sm.sharpe_ratio) AS avg_sharpe,
    AVG(sm.max_drawdown) AS avg_drawdown,
    
    -- Trade stats
    SUM(sm.trade_count) AS total_trades,
    SUM(sm.winning_trades) AS total_winning_trades,
    SUM(sm.losing_trades) AS total_losing_trades,
    
    -- Best/worst performers
    (
        SELECT w2.name
        FROM strategy_metrics sm2
        JOIN wallets w2 ON sm2.wallet_id = w2.id
        WHERE sm2.date = sm.date AND w2.capital_tier = w.capital_tier
        ORDER BY sm2.pnl DESC
        LIMIT 1
    ) AS best_wallet,
    (
        SELECT w2.name
        FROM strategy_metrics sm2
        JOIN wallets w2 ON sm2.wallet_id = w2.id
        WHERE sm2.date = sm.date AND w2.capital_tier = w.capital_tier
        ORDER BY sm2.pnl ASC
        LIMIT 1
    ) AS worst_wallet,
    
    -- Distribution
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY sm.pnl_pct) AS pnl_pct_25th,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY sm.pnl_pct) AS pnl_pct_median,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY sm.pnl_pct) AS pnl_pct_75th

FROM strategy_metrics sm
JOIN wallets w ON sm.wallet_id = w.id
GROUP BY sm.date, w.capital_tier
ORDER BY sm.date DESC, w.capital_tier;

COMMENT ON VIEW strategy_metrics_rollup_daily IS 'Aggregated daily metrics by capital tier for Phase 3 statistical validation';

-- ============================================================================
-- HELPER VIEW: Current Wallet Performance Summary
-- ============================================================================

CREATE OR REPLACE VIEW wallet_performance_summary AS
SELECT 
    w.id,
    w.name,
    w.capital_tier,
    w.initial_balance,
    we.total_equity AS current_equity,
    we.total_pnl,
    we.total_pnl_pct,
    we.position_value,
    
    -- Latest metrics (if available)
    sm.win_rate,
    sm.sharpe_ratio,
    sm.max_drawdown,
    sm.trade_count,
    sm.winning_trades,
    sm.losing_trades,
    
    -- Open positions count
    (
        SELECT COUNT(*)
        FROM positions p
        WHERE p.wallet_id = w.id AND p.closed_at IS NULL
    ) AS open_positions,
    
    -- Last trade time
    (
        SELECT MAX(filled_at)
        FROM trades t
        WHERE t.wallet_id = w.id
    ) AS last_trade_at,
    
    w.created_at

FROM wallets w
LEFT JOIN wallets_equity we ON we.id = w.id
LEFT JOIN LATERAL (
    SELECT *
    FROM strategy_metrics
    WHERE wallet_id = w.id
    ORDER BY date DESC
    LIMIT 1
) sm ON true

ORDER BY w.capital_tier, w.name;

COMMENT ON VIEW wallet_performance_summary IS 'Current snapshot of all wallets with latest metrics';

-- ============================================================================
-- HELPER FUNCTION: Get Top Performers by Tier
-- ============================================================================

CREATE OR REPLACE FUNCTION get_top_performers_by_tier(
    p_tier TEXT,
    p_limit INT DEFAULT 5
)
RETURNS TABLE (
    rank INT,
    wallet_name TEXT,
    equity DECIMAL(15,2),
    pnl DECIMAL(15,2),
    pnl_pct DECIMAL(8,4),
    win_rate DECIMAL(5,4),
    trade_count INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ROW_NUMBER() OVER (ORDER BY we.total_pnl DESC)::INT AS rank,
        w.name AS wallet_name,
        we.total_equity AS equity,
        we.total_pnl AS pnl,
        we.total_pnl_pct AS pnl_pct,
        sm.win_rate,
        sm.trade_count
    FROM wallets w
    LEFT JOIN wallets_equity we ON we.id = w.id
    LEFT JOIN LATERAL (
        SELECT *
        FROM strategy_metrics
        WHERE wallet_id = w.id
        ORDER BY date DESC
        LIMIT 1
    ) sm ON true
    WHERE w.capital_tier = p_tier
    ORDER BY we.total_pnl DESC NULLS LAST
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_top_performers_by_tier IS 'Get top N wallets by PnL for a given tier';
