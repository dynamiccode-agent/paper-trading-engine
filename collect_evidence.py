#!/usr/bin/env python3
"""Collect evidence for Tyler"""
import psycopg2
import sys

DATABASE_URL = "postgresql://neondb_owner:npg_iMO9K8ogQamB@ep-calm-shape-a7sqncxf-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require"

conn = psycopg2.connect(DATABASE_URL)

print("=" * 80)
print("EVIDENCE: ASX PROOF-OF-LIFE EXECUTION")
print("=" * 80)

try:
    with conn.cursor() as cur:
        # Get wallet info
        cur.execute("""
            SELECT id, name
            FROM wallets
            WHERE name = 'Breakout-Tech'
        """)
        wallet = cur.fetchone()
        wallet_id = wallet[0] if wallet else None
        
        print(f"\n1) WALLET")
        print(f"   Name: {wallet[1] if wallet else 'NOT FOUND'}")
        print(f"   ID: {wallet_id}")
        
        # Get latest trade_journal entry for this wallet
        print(f"\n2) LATEST MVJ ENTRY (wallet_id={wallet_id})")
        cur.execute("""
            SELECT 
                id,
                wallet_id,
                ts_utc,
                ticker,
                action,
                mode,
                order_response,
                error
            FROM trade_journal
            WHERE wallet_id = %s
            ORDER BY ts_utc DESC
            LIMIT 1
        """, (wallet_id,))
        
        mvj_row = cur.fetchone()
        if mvj_row:
            print(f"   ✅ MVJ Row ID: {mvj_row[0]}")
            print(f"   wallet_id: {mvj_row[1]}")
            print(f"   ts_utc: {mvj_row[2]}")
            print(f"   ticker: {mvj_row[3]}")
            print(f"   action: {mvj_row[4]}")
            print(f"   mode: {mvj_row[5]}")
            print(f"   order_response: {mvj_row[6]}")
            print(f"   error: {mvj_row[7]}")
        else:
            print(f"   ❌ NO MVJ ROWS for wallet_id={wallet_id}")
        
        # Get latest order for this wallet
        print(f"\n3) LATEST ORDER (wallet_id={wallet_id})")
        cur.execute("""
            SELECT 
                id,
                wallet_id,
                ticker,
                side,
                quantity,
                limit_price,
                status,
                created_at
            FROM orders
            WHERE wallet_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (wallet_id,))
        
        order = cur.fetchone()
        if order:
            print(f"   ✅ Order ID: {order[0]}")
            print(f"   wallet_id: {order[1]}")
            print(f"   ticker: {order[2]}")
            print(f"   side: {order[3]}")
            print(f"   quantity: {order[4]}")
            print(f"   limit_price: {order[5]}")
            print(f"   status: {order[6]}")
            print(f"   created_at: {order[7]}")
        else:
            print(f"   ❌ NO ORDERS for wallet_id={wallet_id}")
        
        # Count errors in last 3 cycles (last 3 minutes)
        print(f"\n4) ERROR COUNT (last 3 minutes)")
        cur.execute("""
            SELECT COUNT(*)
            FROM trade_journal
            WHERE wallet_id = %s
            AND ts_utc >= NOW() - INTERVAL '3 minutes'
            AND error IS NOT NULL
        """, (wallet_id,))
        error_count = cur.fetchone()[0]
        print(f"   Errors: {error_count}")
        if error_count == 0:
            print(f"   ✅ 0 ERRORS")
        else:
            print(f"   ❌ {error_count} ERRORS DETECTED")

except Exception as e:
    print(f"❌ ERROR: {e}")
    sys.exit(1)
finally:
    conn.close()

print("\n" + "=" * 80)
