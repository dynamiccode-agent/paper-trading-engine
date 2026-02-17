#!/usr/bin/env python3
"""
Create 10 Strategy Wallets - $10K each
Each wallet represents a different trading strategy/approach
"""
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))

import psycopg2
from psycopg2.extras import RealDictCursor

# Register UUID adapter
psycopg2.extensions.register_adapter(type(uuid4()), lambda val: psycopg2.extensions.AsIs(f"'{val}'"))

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# 10 different strategy wallets
STRATEGY_WALLETS = [
    {'name': 'Momentum-Long', 'description': 'High momentum uptrend stocks'},
    {'name': 'Value-Deep', 'description': 'Deep value undervalued stocks'},
    {'name': 'Breakout-Tech', 'description': 'Tech sector breakout patterns'},
    {'name': 'Mean-Reversion', 'description': 'Oversold bounce plays'},
    {'name': 'Growth-Quality', 'description': 'High-quality growth stocks'},
    {'name': 'Dividend-Yield', 'description': 'Dividend aristocrats'},
    {'name': 'Small-Cap-Growth', 'description': 'Small cap growth momentum'},
    {'name': 'Sector-Rotation', 'description': 'Sector rotation strategy'},
    {'name': 'Volatility-Long', 'description': 'Long volatility plays'},
    {'name': 'Options-Hedged', 'description': 'Options-hedged equity'},
]

INITIAL_BALANCE = 10000.00
TIER = '10k'

print("="*70)
print("CREATING 10 STRATEGY WALLETS - $10K EACH")
print("="*70)
print()

conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
created = 0
skipped = 0

try:
    with conn.cursor() as cur:
        for wallet in STRATEGY_WALLETS:
            name = wallet['name']
            description = wallet['description']
            
            # Check if exists
            cur.execute("SELECT id FROM wallets WHERE name = %s", (name,))
            if cur.fetchone():
                print(f"⏭️  {name}: Already exists")
                skipped += 1
                continue
            
            # Create
            wallet_id = uuid4()
            cur.execute("""
                INSERT INTO wallets (
                    id, name, capital_tier, initial_balance, current_balance
                ) VALUES (
                    %s, %s, %s, %s, %s
                )
            """, (wallet_id, name, TIER, INITIAL_BALANCE, INITIAL_BALANCE))
            
            print(f"✅ {name}: ${INITIAL_BALANCE:,.2f} ({description})")
            created += 1
        
        conn.commit()
        
        print()
        print("="*70)
        print(f"✅ Created: {created}")
        print(f"⏭️  Skipped: {skipped}")
        print(f"💰 Total Capital: ${(created * INITIAL_BALANCE):,.2f}")
        print("="*70)

except Exception as e:
    conn.rollback()
    print(f"❌ Error: {e}")
    raise
finally:
    conn.close()
