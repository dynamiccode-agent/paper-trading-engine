#!/usr/bin/env python
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = 'postgresql://neondb_owner:npg_iMO9K8ogQamB@ep-calm-shape-a7sqncxf-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require'

conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
with conn.cursor() as cur:
    # Check total US instruments
    cur.execute("SELECT COUNT(*) as total, MAX(timestamp) as last_update FROM instruments WHERE market = 'US'")
    result = cur.fetchone()
    print(f"📊 Total US instruments: {result['total']}")
    print(f"⏰ Last update: {result['last_update']}")
    
    # Check signals in last 24h
    cur.execute("SELECT COUNT(*) as cnt FROM instruments WHERE market = 'US' AND timestamp > NOW() - INTERVAL '24 hours'")
    count = cur.fetchone()['cnt']
    print(f"📈 Signals (last 24h): {count}")
    
    # Check score distribution
    cur.execute("""
        SELECT 
            MIN(score) as min_score,
            MAX(score) as max_score,
            AVG(score) as avg_score,
            COUNT(CASE WHEN score >= 70 THEN 1 END) as count_70plus
        FROM instruments 
        WHERE market = 'US' 
        AND timestamp > NOW() - INTERVAL '24 hours'
    """)
    result = cur.fetchone()
    if result['min_score'] is not None:
        print(f"🎯 Score range: {result['min_score']:.1f} - {result['max_score']:.1f} (avg: {result['avg_score']:.1f})")
        print(f"⭐ Signals >= 70: {result['count_70plus']}")
    
    # Check top 5 signals
    cur.execute("""
        SELECT ticker, score, ROUND(price::numeric, 2) as price, regime, confidence
        FROM instruments
        WHERE market = 'US'
        AND timestamp > NOW() - INTERVAL '24 hours'
        ORDER BY score DESC
        LIMIT 5
    """)
    signals = cur.fetchall()
    if signals:
        print(f"\n🏆 Top 5 signals:")
        for i, s in enumerate(signals, 1):
            print(f"  {i}. {s['ticker']}: score={s['score']:.1f}, price=${s['price']}, regime={s['regime']}, conf={s['confidence']:.1f}")
    else:
        print("❌ No signals found in last 24h")
conn.close()
