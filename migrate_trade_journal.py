import os
import sys

# Try to find a working postgres library
try:
    import psycopg2
    use_psycopg2 = True
except ImportError:
    try:
        from urllib.parse import urlparse
        import pg8000.native
        use_psycopg2 = False
    except ImportError:
        print("ERROR: No PostgreSQL library found (psycopg2 or pg8000)")
        sys.exit(1)

DATABASE_URL = os.environ['DATABASE_URL']

sql = """
CREATE TABLE IF NOT EXISTS trade_journal (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL,
    order_id UUID,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    outcome TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_journal_wallet ON trade_journal(wallet_id);
CREATE INDEX IF NOT EXISTS idx_trade_journal_created ON trade_journal(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_journal_ticker ON trade_journal(ticker);
"""

if use_psycopg2:
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    conn.close()
else:
    # Parse DATABASE_URL for pg8000
    parsed = urlparse(DATABASE_URL)
    conn = pg8000.native.Connection(
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        database=parsed.path[1:],
        port=parsed.port or 5432,
        ssl_context=True
    )
    conn.run(sql)
    conn.close()

print("✅ trade_journal table created")
