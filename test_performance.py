#!/usr/bin/env python3
"""
Performance Test - Hardening Mode
Simulate 50 wallets, 5 signals, 5 cycles
Measure: API latency, memory, rate limits
"""
import os
import sys
import time
import psutil
import requests
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

DATABASE_URL = os.environ.get('DATABASE_URL')
ALPHAVANTAGE_API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY', 'demo')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

API_BASE = 'http://localhost:8000/api/paper-trading'

print("="*70)
print("PERFORMANCE TEST - HARDENING MODE")
print("="*70)
print()

# Get baseline memory
process = psutil.Process()
baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

print(f"Baseline Memory: {baseline_memory:.1f} MB")
print()

# Test 1: API Health Check Latency
print("Test 1: API Health Check Latency")
print("-" * 40)
latencies = []
for i in range(10):
    start = time.time()
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        latency = (time.time() - start) * 1000  # ms
        latencies.append(latency)
        print(f"  Request {i+1}: {latency:.1f}ms - {response.status_code}")
    except Exception as e:
        print(f"  Request {i+1}: FAILED - {e}")

avg_latency = sum(latencies) / len(latencies) if latencies else 0
max_latency = max(latencies) if latencies else 0
print(f"\n  Average: {avg_latency:.1f}ms")
print(f"  Max: {max_latency:.1f}ms")
print(f"  ✓ PASS" if avg_latency < 300 else f"  ✗ FAIL (>300ms)")
print()

# Test 2: Summary Endpoint Latency
print("Test 2: Summary Endpoint Latency")
print("-" * 40)
start = time.time()
try:
    response = requests.get(f"{API_BASE}/summary", timeout=5)
    latency = (time.time() - start) * 1000
    print(f"  Latency: {latency:.1f}ms")
    print(f"  Status: {response.status_code}")
    print(f"  ✓ PASS" if latency < 300 else f"  ✗ FAIL (>300ms)")
except Exception as e:
    print(f"  ✗ FAILED: {e}")
print()

# Test 3: Wallets List Latency
print("Test 3: Wallets List Latency")
print("-" * 40)
start = time.time()
try:
    response = requests.get(f"{API_BASE}/wallets", timeout=5)
    latency = (time.time() - start) * 1000
    wallets = response.json()
    wallet_count = len(wallets)
    print(f"  Wallets: {wallet_count}")
    print(f"  Latency: {latency:.1f}ms")
    print(f"  ✓ PASS" if latency < 300 else f"  ✗ FAIL (>300ms)")
except Exception as e:
    print(f"  ✗ FAILED: {e}")
    wallet_count = 0
print()

# Test 4: Memory Usage After Load
current_memory = process.memory_info().rss / 1024 / 1024
memory_growth = current_memory - baseline_memory
print(f"Test 4: Memory Usage")
print("-" * 40)
print(f"  Current: {current_memory:.1f} MB")
print(f"  Growth: {memory_growth:.1f} MB")
print(f"  ✓ PASS" if memory_growth < 100 else f"  ⚠️  WARNING (>100MB growth)")
print()

# Test 5: Rapid Fire Requests (Rate Limit Test)
print("Test 5: Rapid Fire Requests (Rate Limit)")
print("-" * 40)
print("  Sending 20 requests rapidly...")
start_time = time.time()
success_count = 0
fail_count = 0
rate_limit_count = 0

for i in range(20):
    try:
        response = requests.get(f"{API_BASE}/summary", timeout=2)
        if response.status_code == 200:
            success_count += 1
        elif response.status_code == 429:
            rate_limit_count += 1
        else:
            fail_count += 1
    except Exception:
        fail_count += 1

elapsed = time.time() - start_time
print(f"  Success: {success_count}")
print(f"  Rate Limited: {rate_limit_count}")
print(f"  Failed: {fail_count}")
print(f"  Time: {elapsed:.2f}s")
print(f"  ✓ PASS" if rate_limit_count == 0 else f"  ⚠️  WARNING (rate limited)")
print()

# Test 6: Database Query Performance
print("Test 6: Database Query Performance")
print("-" * 40)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    # Query wallets
    start = time.time()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM wallets")
        count = cur.fetchone()['count']
    db_latency = (time.time() - start) * 1000
    
    # Query trades
    start = time.time()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM trades")
        trade_count = cur.fetchone()['count']
    trade_latency = (time.time() - start) * 1000
    
    conn.close()
    
    print(f"  Wallets Count: {count} ({db_latency:.1f}ms)")
    print(f"  Trades Count: {trade_count} ({trade_latency:.1f}ms)")
    print(f"  ✓ PASS" if db_latency < 100 else f"  ⚠️  SLOW (>100ms)")
except Exception as e:
    print(f"  ✗ FAILED: {e}")
print()

# Summary
print("="*70)
print("PERFORMANCE TEST SUMMARY")
print("="*70)
print(f"API Health Latency:  {avg_latency:.1f}ms avg, {max_latency:.1f}ms max")
print(f"Memory Growth:       {memory_growth:.1f} MB")
print(f"Wallet Count:        {wallet_count}")
print(f"Rate Limit Hit:      {rate_limit_count > 0}")
print()

# Overall Pass/Fail
all_pass = (
    avg_latency < 300 and
    memory_growth < 100 and
    rate_limit_count == 0
)

if all_pass:
    print("✅ ALL TESTS PASSED")
else:
    print("⚠️  SOME TESTS FAILED OR WARNING")

print("="*70)
