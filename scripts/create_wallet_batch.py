#!/usr/bin/env python3
"""
Batch Wallet Creator - Phase 3

Creates 50 wallets across 5 capital tiers:
- 10× $1k   (T1-001 through T1-010)
- 10× $10k  (T2-001 through T2-010)
- 10× $20k  (T3-001 through T3-010)
- 10× $40k  (T4-001 through T4-010)
- 10× $50k  (T5-001 through T5-010)

Usage:
    export DATABASE_URL="postgresql://..."
    python scripts/create_wallet_batch.py [--dry-run]
"""
import os
import sys
from uuid import uuid4
import argparse

# Add lib to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import psycopg2
from psycopg2.extras import RealDictCursor

# Register UUID adapter
psycopg2.extensions.register_adapter(type(uuid4()), lambda val: psycopg2.extensions.AsIs(f"'{val}'"))

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# Wallet tiers configuration
WALLET_TIERS = [
    {'tier': 'T1', 'tier_name': '1k', 'balance': 1000.00, 'count': 10},
    {'tier': 'T2', 'tier_name': '10k', 'balance': 10000.00, 'count': 10},
    {'tier': 'T3', 'tier_name': '20k', 'balance': 20000.00, 'count': 10},
    {'tier': 'T4', 'tier_name': '40k', 'balance': 40000.00, 'count': 10},
    {'tier': 'T5', 'tier_name': '50k', 'balance': 50000.00, 'count': 10},
]


def create_wallet_batch(dry_run=False):
    """Create wallet batch"""
    print("\n" + "="*70)
    print("WALLET BATCH CREATION - PHASE 3")
    print("="*70)
    
    total_wallets = sum(t['count'] for t in WALLET_TIERS)
    total_capital = sum(t['balance'] * t['count'] for t in WALLET_TIERS)
    
    print(f"\nPlan:")
    print(f"  Total Wallets: {total_wallets}")
    print(f"  Total Capital: ${total_capital:,.2f}")
    print()
    
    for tier in WALLET_TIERS:
        print(f"  {tier['tier']}: {tier['count']}× ${tier['balance']:,.2f} = ${tier['balance'] * tier['count']:,.2f}")
    
    if dry_run:
        print("\n🔬 DRY RUN MODE - No wallets will be created")
        return
    
    print("\n" + "="*70)
    print("Creating wallets...")
    print("="*70)
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    created_count = 0
    skipped_count = 0
    
    try:
        with conn.cursor() as cur:
            for tier_config in WALLET_TIERS:
                tier = tier_config['tier']
                tier_name = tier_config['tier_name']
                balance = tier_config['balance']
                count = tier_config['count']
                
                print(f"\n📊 {tier} ({tier_name}):")
                
                for i in range(1, count + 1):
                    wallet_name = f"{tier}-{i:03d}"
                    
                    # Check if already exists
                    cur.execute("""
                        SELECT id FROM wallets WHERE name = %s
                    """, (wallet_name,))
                    
                    if cur.fetchone():
                        print(f"   ⏭️  {wallet_name}: Already exists")
                        skipped_count += 1
                        continue
                    
                    # Create wallet
                    wallet_id = uuid4()
                    cur.execute("""
                        INSERT INTO wallets (
                            id, name, capital_tier, initial_balance, current_balance
                        ) VALUES (
                            %s, %s, %s, %s, %s
                        )
                    """, (wallet_id, wallet_name, tier_name, balance, balance))
                    
                    print(f"   ✅ {wallet_name}: {wallet_id}")
                    created_count += 1
            
            conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        conn.close()
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"✅ Created: {created_count}")
    print(f"⏭️  Skipped: {skipped_count} (already existed)")
    print(f"📊 Total Wallets: {created_count + skipped_count}")


def list_wallets():
    """List all wallets by tier"""
    print("\n" + "="*70)
    print("EXISTING WALLETS")
    print("="*70)
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT capital_tier, COUNT(*) as count, SUM(initial_balance) as total_capital
                FROM wallets
                GROUP BY capital_tier
                ORDER BY 
                    CASE capital_tier
                        WHEN '1k' THEN 1
                        WHEN '10k' THEN 2
                        WHEN '20k' THEN 3
                        WHEN '40k' THEN 4
                        WHEN '50k' THEN 5
                        ELSE 99
                    END
            """)
            
            rows = cur.fetchall()
            
            if not rows:
                print("\nNo wallets found")
                return
            
            total_wallets = 0
            total_capital = 0
            
            print()
            for row in rows:
                tier = row['capital_tier']
                count = row['count']
                capital = row['total_capital']
                
                print(f"  {tier}: {count} wallets, ${capital:,.2f} capital")
                
                total_wallets += count
                total_capital += capital
            
            print(f"\n  TOTAL: {total_wallets} wallets, ${total_capital:,.2f} capital")
    
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Batch Wallet Creator')
    parser.add_argument('--dry-run', action='store_true', help='Show plan without creating')
    parser.add_argument('--list', action='store_true', help='List existing wallets')
    args = parser.parse_args()
    
    if args.list:
        list_wallets()
    else:
        create_wallet_batch(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
