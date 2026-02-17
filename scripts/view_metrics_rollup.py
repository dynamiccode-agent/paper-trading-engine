#!/usr/bin/env python3
"""
View Strategy Metrics Rollup - Phase 3

Query aggregated performance metrics by capital tier

Usage:
    export DATABASE_URL="postgresql://..."
    python scripts/view_metrics_rollup.py [--date YYYY-MM-DD] [--tier T1]
"""
import os
import sys
from datetime import datetime, date
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


def view_daily_rollup(target_date=None, tier=None):
    """View daily metrics rollup"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    try:
        with conn.cursor() as cur:
            # Build query
            where_clauses = []
            params = []
            
            if target_date:
                where_clauses.append("date = %s")
                params.append(target_date)
            
            if tier:
                where_clauses.append("capital_tier = %s")
                params.append(tier)
            
            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            cur.execute(f"""
                SELECT * FROM strategy_metrics_rollup_daily
                {where_sql}
                ORDER BY date DESC, capital_tier
                LIMIT 20
            """, tuple(params))
            
            rows = cur.fetchall()
            
            if not rows:
                print("\nNo metrics found")
                return
            
            print("\n" + "="*120)
            print("STRATEGY METRICS ROLLUP (Daily by Tier)")
            print("="*120)
            
            for row in rows:
                print(f"\n📅 {row['date']} - {row['capital_tier']}")
                print(f"   Wallets: {row['wallet_count']}")
                print(f"   Avg Equity: ${row['avg_equity']:,.2f} (min: ${row['min_equity']:,.2f}, max: ${row['max_equity']:,.2f})")
                print(f"   Total PnL: ${row['total_pnl']:,.2f}")
                print(f"   Avg PnL%: {row['avg_pnl_pct']:.2f}% (min: {row['min_pnl_pct']:.2f}%, max: {row['max_pnl_pct']:.2f}%)")
                print(f"   Avg Win Rate: {row['avg_win_rate']*100 if row['avg_win_rate'] else 0:.1f}%")
                print(f"   Total Trades: {row['total_trades']} (W: {row['total_winning_trades']}, L: {row['total_losing_trades']})")
                print(f"   Best: {row['best_wallet']}, Worst: {row['worst_wallet']}")
                print(f"   PnL% Distribution: 25th={row['pnl_pct_25th']:.2f}%, median={row['pnl_pct_median']:.2f}%, 75th={row['pnl_pct_75th']:.2f}%")
    
    finally:
        conn.close()


def view_wallet_summary():
    """View all wallets performance summary"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM wallet_performance_summary
                ORDER BY capital_tier, total_pnl DESC NULLS LAST
            """)
            
            rows = cur.fetchall()
            
            if not rows:
                print("\nNo wallets found")
                return
            
            print("\n" + "="*120)
            print("WALLET PERFORMANCE SUMMARY")
            print("="*120)
            
            current_tier = None
            for row in rows:
                if row['capital_tier'] != current_tier:
                    current_tier = row['capital_tier']
                    print(f"\n📊 {current_tier.upper()}:")
                
                pnl_str = f"${row['total_pnl']:,.2f}" if row['total_pnl'] else "$0.00"
                pnl_pct_str = f"({row['total_pnl_pct']:+.2f}%)" if row['total_pnl_pct'] else "(+0.00%)"
                
                win_rate_str = f"{row['win_rate']*100:.1f}%" if row['win_rate'] else "N/A"
                trades_str = f"{row['trade_count']}" if row['trade_count'] else "0"
                
                print(f"   {row['name']}: equity=${row['current_equity']:,.2f}, pnl={pnl_str} {pnl_pct_str}, "
                      f"positions={row['open_positions']}, win_rate={win_rate_str}, trades={trades_str}")
    
    finally:
        conn.close()


def view_top_performers(tier, limit=5):
    """View top performers by tier"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM get_top_performers_by_tier(%s, %s)
            """, (tier, limit))
            
            rows = cur.fetchall()
            
            if not rows:
                print(f"\nNo wallets found for tier {tier}")
                return
            
            print(f"\n🏆 TOP {limit} PERFORMERS - {tier.upper()}")
            print("="*80)
            
            for row in rows:
                pnl_str = f"${row['pnl']:,.2f}" if row['pnl'] else "$0.00"
                pnl_pct_str = f"({row['pnl_pct']:+.2f}%)" if row['pnl_pct'] else "(+0.00%)"
                win_rate_str = f"{row['win_rate']*100:.1f}%" if row['win_rate'] else "N/A"
                
                print(f"   #{row['rank']} {row['wallet_name']}: {pnl_str} {pnl_pct_str}, "
                      f"equity=${row['equity']:,.2f}, win_rate={win_rate_str}, trades={row['trade_count']}")
    
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='View Strategy Metrics Rollup')
    parser.add_argument('--date', type=str, help='Filter by date (YYYY-MM-DD)')
    parser.add_argument('--tier', type=str, help='Filter by tier (1k, 10k, 20k, 40k, 50k)')
    parser.add_argument('--wallets', action='store_true', help='Show wallet summary')
    parser.add_argument('--top', type=str, help='Show top performers for tier (T1, T2, T3, T4, T5)')
    parser.add_argument('--limit', type=int, default=5, help='Number of top performers')
    args = parser.parse_args()
    
    if args.wallets:
        view_wallet_summary()
    elif args.top:
        view_top_performers(args.top, args.limit)
    else:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date() if args.date else None
        view_daily_rollup(target_date=target_date, tier=args.tier)


if __name__ == '__main__':
    main()
