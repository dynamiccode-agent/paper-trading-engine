"""
Paper Trading HTTP API - Phase 4

FastAPI service for Parallax UI integration

Endpoints:
- GET /api/paper-trading/summary
- GET /api/paper-trading/wallets
- GET /api/paper-trading/wallets/:id
- GET /api/paper-trading/wallets/:id/trades  
- GET /api/paper-trading/trades
- GET /api/paper-trading/analytics
- GET /api/paper-trading/overnight
- POST /api/paper-trading/run-cycle (admin)
"""
import os
import sys
from datetime import datetime, date, timedelta
from typing import List, Optional
from decimal import Decimal

# Add parent dir to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

# Environment
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

# FastAPI app
app = FastAPI(
    title="Paper Trading API",
    description="HTTP API for Parallax Paper Trading integration",
    version="1.0.0"
)

# CORS for local development (Tauri app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://localhost:1420", "*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database helper
def get_db():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# Response models
class MarketStatus(BaseModel):
    market: str
    is_open: bool
    local_time: str
    next_open: Optional[str]

class SummaryResponse(BaseModel):
    market_status: MarketStatus
    total_capital: float
    total_equity: float
    total_pnl: float
    total_pnl_pct: float
    wallet_count: int
    active_positions: int
    best_wallet: Optional[dict]
    worst_wallet: Optional[dict]
    last_cycle: Optional[str]
    api_health: str

class WalletResponse(BaseModel):
    id: str
    name: str
    capital_tier: str
    initial_balance: float
    current_balance: float
    equity: float
    pnl: float
    pnl_pct: float
    position_value: float
    open_positions: int
    win_rate: Optional[float]
    trade_count: Optional[int]

# ===========================================================================
# ENDPOINTS
# ===========================================================================

@app.get("/")
def root():
    """Health check"""
    return {"status": "ok", "service": "paper-trading-api", "version": "1.0.0"}

@app.get("/api/paper-trading/health")
def get_health():
    """
    System health check - critical for production monitoring
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # DB connectivity test
            cur.execute("SELECT 1")
            db_status = "connected"
            
            # Last market data fetch
            cur.execute("""
                SELECT MAX(fetched_at) as last_fetch
                FROM market_data
            """)
            result = cur.fetchone()
            last_market_fetch_at = result['last_fetch'].isoformat() if result and result['last_fetch'] else None
            
            # Last strategy cycle (latest trade)
            cur.execute("""
                SELECT MAX(filled_at) as last_trade
                FROM trades
            """)
            result = cur.fetchone()
            last_cycle_at = result['last_trade'].isoformat() if result and result['last_trade'] else None
            
            # Check market data provider status
            from lib.market_data import AlphaVantageProvider
            # In production, we'd track this in-memory or Redis
            # For now, return "ok" if no circuit breaker stored
            breaker_status = "ok"  # TODO: Store breaker state globally
            
            # API request tracking (would need middleware for accurate count)
            req_per_minute = 0  # TODO: Add request counter middleware
            
            return {
                "api_status": "ok",
                "db_status": db_status,
                "breaker_status": breaker_status,
                "last_cycle_at": last_cycle_at,
                "last_market_fetch_at": last_market_fetch_at,
                "req_per_minute": req_per_minute,
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        return {
            "api_status": "error",
            "db_status": "error",
            "breaker_status": "unknown",
            "last_cycle_at": None,
            "last_market_fetch_at": None,
            "req_per_minute": 0,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/api/paper-trading/summary")
def get_summary():
    """
    Dashboard summary
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Get wallet stats
            cur.execute("""
                SELECT 
                    COUNT(*) as wallet_count,
                    SUM(initial_balance) as total_capital,
                    SUM(total_equity) as total_equity,
                    SUM(total_pnl) as total_pnl,
                    AVG(total_pnl_pct) as avg_pnl_pct
                FROM wallets_equity
            """)
            stats = cur.fetchone()
            
            # Get active positions count
            cur.execute("""
                SELECT COUNT(*) as count
                FROM positions
                WHERE closed_at IS NULL
            """)
            active_positions = cur.fetchone()['count']
            
            # Get best/worst wallets
            cur.execute("""
                SELECT w.name, we.total_pnl
                FROM wallets w
                JOIN wallets_equity we ON we.id = w.id
                ORDER BY we.total_pnl DESC NULLS LAST
                LIMIT 1
            """)
            best_wallet = cur.fetchone()
            
            cur.execute("""
                SELECT w.name, we.total_pnl
                FROM wallets w
                JOIN wallets_equity we ON we.id = w.id
                ORDER BY we.total_pnl ASC NULLS LAST
                LIMIT 1
            """)
            worst_wallet = cur.fetchone()
            
            # Market status (simple - can enhance later)
            from lib.market_session import MarketSession
            market_status = MarketSession.get_market_status('US')
            
            return {
                "market_status": market_status,
                "total_capital": float(stats['total_capital'] or 0),
                "total_equity": float(stats['total_equity'] or 0),
                "total_pnl": float(stats['total_pnl'] or 0),
                "total_pnl_pct": float(stats['avg_pnl_pct'] or 0),
                "wallet_count": stats['wallet_count'],
                "active_positions": active_positions,
                "best_wallet": dict(best_wallet) if best_wallet else None,
                "worst_wallet": dict(worst_wallet) if worst_wallet else None,
                "last_cycle": None,  # TODO: Track last execution time
                "api_health": "ok"
            }
    finally:
        conn.close()

@app.get("/api/paper-trading/wallets")
def get_wallets(
    tier: Optional[str] = Query(None, description="Filter by capital tier"),
    sort_by: Optional[str] = Query("pnl", description="Sort field"),
    order: Optional[str] = Query("desc", description="Sort order (asc/desc)")
):
    """
    List all wallets with performance metrics
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Build query
            where_clause = f"WHERE w.capital_tier = '{tier}'" if tier else ""
            order_clause = f"ORDER BY we.total_pnl {'DESC' if order == 'desc' else 'ASC'} NULLS LAST"
            
            cur.execute(f"""
                SELECT 
                    w.id::text,
                    w.name,
                    w.capital_tier,
                    w.initial_balance,
                    w.current_balance,
                    we.total_equity,
                    we.total_pnl,
                    we.total_pnl_pct,
                    we.position_value,
                    (SELECT COUNT(*) FROM positions p WHERE p.wallet_id = w.id AND p.closed_at IS NULL) as open_positions,
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
                {where_clause}
                {order_clause}
            """)
            
            rows = cur.fetchall()
            
            return [
                {
                    "id": row['id'],
                    "name": row['name'],
                    "capital_tier": row['capital_tier'],
                    "initial_balance": float(row['initial_balance']),
                    "current_balance": float(row['current_balance']),
                    "equity": float(row['total_equity'] or 0),
                    "pnl": float(row['total_pnl'] or 0),
                    "pnl_pct": float(row['total_pnl_pct'] or 0),
                    "position_value": float(row['position_value'] or 0),
                    "open_positions": row['open_positions'],
                    "win_rate": float(row['win_rate'] or 0) if row['win_rate'] else None,
                    "trade_count": row['trade_count']
                }
                for row in rows
            ]
    finally:
        conn.close()

@app.get("/api/paper-trading/wallets/{wallet_id}")
def get_wallet_detail(wallet_id: str):
    """
    Get wallet detail with positions and metrics
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Get wallet with equity
            cur.execute("""
                SELECT 
                    w.id::text,
                    w.name,
                    w.capital_tier,
                    w.initial_balance,
                    w.current_balance,
                    w.reserved_balance,
                    w.buying_power,
                    we.total_equity,
                    we.total_pnl,
                    we.total_pnl_pct,
                    we.position_value
                FROM wallets w
                LEFT JOIN wallets_equity we ON we.id = w.id
                WHERE w.id = %s
            """, (wallet_id,))
            
            wallet = cur.fetchone()
            
            if not wallet:
                raise HTTPException(status_code=404, detail="Wallet not found")
            
            # EQUITY CONSISTENCY CHECK
            computed_equity = wallet['current_balance'] + (wallet['position_value'] or 0)
            stored_equity = wallet['total_equity'] or 0
            equity_diff = abs(computed_equity - stored_equity)
            equity_mismatch = equity_diff > 0.01  # 1 cent threshold
            
            if equity_mismatch:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"EQUITY MISMATCH DETECTED: Wallet {wallet_id} "
                    f"computed={computed_equity:.2f} stored={stored_equity:.2f} "
                    f"diff={equity_diff:.2f}"
                )
            
            # Get open positions
            cur.execute("""
                SELECT 
                    p.id::text,
                    p.ticker,
                    p.market,
                    p.quantity,
                    p.avg_entry_price,
                    p.total_cost,
                    p.realised_pnl,
                    md.price as current_price,
                    (md.price * p.quantity) as current_value,
                    ((md.price * p.quantity) - p.total_cost) as unrealised_pnl,
                    (((md.price * p.quantity) - p.total_cost) / NULLIF(p.total_cost, 0) * 100) as unrealised_pnl_pct
                FROM positions p
                LEFT JOIN LATERAL (
                    SELECT price
                    FROM market_data
                    WHERE ticker = p.ticker AND market = p.market
                    ORDER BY timestamp DESC
                    LIMIT 1
                ) md ON true
                WHERE p.wallet_id = %s AND p.closed_at IS NULL
                ORDER BY p.opened_at DESC
            """, (wallet_id,))
            
            positions = cur.fetchall()
            
            # Get latest metrics
            cur.execute("""
                SELECT *
                FROM strategy_metrics
                WHERE wallet_id = %s
                ORDER BY date DESC
                LIMIT 30
            """, (wallet_id,))
            
            metrics = cur.fetchall()
            
            return {
                "wallet": dict(wallet),
                "positions": [dict(p) for p in positions],
                "metrics": [
                    {
                        "date": str(m['date']),
                        "equity": float(m['equity']),
                        "pnl": float(m['pnl']),
                        "pnl_pct": float(m['pnl_pct']),
                        "win_rate": float(m['win_rate'] or 0) if m['win_rate'] else None,
                        "trade_count": m['trade_count']
                    }
                    for m in metrics
                ],
                "equity_mismatch": equity_mismatch,
                "equity_diff": float(equity_diff) if equity_mismatch else 0.0
            }
    finally:
        conn.close()

@app.get("/api/paper-trading/wallets/{wallet_id}/trades")
def get_wallet_trades(
    wallet_id: str,
    limit: int = Query(50, description="Number of trades to return")
):
    """
    Get trades for a specific wallet
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    t.id::text,
                    t.ticker,
                    t.market,
                    t.side,
                    t.quantity,
                    t.fill_price,
                    t.slippage_bps,
                    t.commission,
                    t.gross_amount,
                    t.net_amount,
                    t.filled_at,
                    t.oracle_signal
                FROM trades t
                WHERE t.wallet_id = %s
                ORDER BY t.filled_at DESC
                LIMIT %s
            """, (wallet_id, limit))
            
            trades = cur.fetchall()
            
            return [dict(t) for t in trades]
    finally:
        conn.close()

@app.get("/api/paper-trading/trades")
def get_all_trades(
    wallet_id: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    limit: int = Query(100)
):
    """
    Get global trade ledger
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            where_clauses = []
            params = []
            
            if wallet_id:
                where_clauses.append("t.wallet_id = %s")
                params.append(wallet_id)
            
            if ticker:
                where_clauses.append("t.ticker = %s")
                params.append(ticker)
            
            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            params.append(limit)
            
            cur.execute(f"""
                SELECT 
                    t.id::text,
                    t.wallet_id::text,
                    w.name as wallet_name,
                    t.ticker,
                    t.market,
                    t.side,
                    t.quantity,
                    t.fill_price,
                    t.slippage_bps,
                    t.commission,
                    t.gross_amount,
                    t.net_amount,
                    t.filled_at
                FROM trades t
                JOIN wallets w ON w.id = t.wallet_id
                {where_sql}
                ORDER BY t.filled_at DESC
                LIMIT %s
            """, tuple(params))
            
            trades = cur.fetchall()
            
            return [dict(t) for t in trades]
    finally:
        conn.close()

@app.get("/api/paper-trading/analytics")
def get_analytics(target_date: Optional[str] = Query(None)):
    """
    Get aggregated analytics from rollup views
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Parse date
            if target_date:
                date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
            else:
                date_obj = date.today()
            
            # Get daily rollup by tier
            cur.execute("""
                SELECT *
                FROM strategy_metrics_rollup_daily
                WHERE date = %s
                ORDER BY capital_tier
            """, (date_obj,))
            
            rollup = cur.fetchall()
            
            # Get top performers by tier
            tiers = ['1k', '10k', '20k', '40k', '50k']
            top_performers = {}
            
            for tier in tiers:
                cur.execute("""
                    SELECT * FROM get_top_performers_by_tier(%s, 5)
                """, (tier,))
                top_performers[tier] = [dict(row) for row in cur.fetchall()]
            
            return {
                "date": str(date_obj),
                "rollup_by_tier": [dict(r) for r in rollup],
                "top_performers_by_tier": top_performers
            }
    finally:
        conn.close()

@app.get("/api/paper-trading/overnight")
def get_overnight_summary():
    """
    Overnight summary: what happened while you slept
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            yesterday = date.today() - timedelta(days=1)
            today = date.today()
            
            # Get PnL change per tier
            cur.execute("""
                SELECT 
                    capital_tier,
                    SUM(pnl) as tier_pnl,
                    AVG(pnl_pct) as avg_pnl_pct,
                    COUNT(*) as wallet_count
                FROM strategy_metrics
                WHERE date >= %s
                GROUP BY capital_tier
                ORDER BY capital_tier
            """, (yesterday,))
            
            tier_performance = cur.fetchall()
            
            # Get top 5 winners
            cur.execute("""
                SELECT 
                    w.name,
                    w.capital_tier,
                    sm.pnl,
                    sm.pnl_pct
                FROM strategy_metrics sm
                JOIN wallets w ON w.id = sm.wallet_id
                WHERE sm.date >= %s
                ORDER BY sm.pnl DESC
                LIMIT 5
            """, (yesterday,))
            
            winners = cur.fetchall()
            
            # Get top 5 losers
            cur.execute("""
                SELECT 
                    w.name,
                    w.capital_tier,
                    sm.pnl,
                    sm.pnl_pct
                FROM strategy_metrics sm
                JOIN wallets w ON w.id = sm.wallet_id
                WHERE sm.date >= %s
                ORDER BY sm.pnl ASC
                LIMIT 5
            """, (yesterday,))
            
            losers = cur.fetchall()
            
            # Get notable trades (largest moves)
            cur.execute("""
                SELECT 
                    t.ticker,
                    t.side,
                    t.quantity,
                    t.fill_price,
                    t.net_amount,
                    w.name as wallet_name,
                    t.filled_at
                FROM trades t
                JOIN wallets w ON w.id = t.wallet_id
                WHERE t.filled_at >= %s
                ORDER BY ABS(t.net_amount) DESC
                LIMIT 10
            """, (yesterday,))
            
            notable_trades = cur.fetchall()
            
            return {
                "period": f"{yesterday} to {today}",
                "tier_performance": [dict(t) for t in tier_performance],
                "top_winners": [dict(w) for w in winners],
                "top_losers": [dict(l) for l in losers],
                "notable_trades": [dict(t) for t in notable_trades],
                "summary": f"Overnight: {len(notable_trades)} trades executed across {len(tier_performance)} tiers"
            }
    finally:
        conn.close()

# Run with: uvicorn api.main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
