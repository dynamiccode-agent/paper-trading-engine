#!/usr/bin/env python3
"""
Apply database migrations for paper trading module
"""
import os
import sys
import psycopg2
from pathlib import Path

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

MIGRATIONS_DIR = Path(__file__).parent / 'migrations'

def apply_migration(migration_file):
    """Apply a single migration file"""
    print(f"Applying migration: {migration_file.name}")
    
    with open(migration_file, 'r') as f:
        sql = f.read()
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print(f"✅ Migration {migration_file.name} applied successfully")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration {migration_file.name} failed: {e}")
        return False
    finally:
        conn.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python apply_migration.py <migration_number>")
        print("Example: python apply_migration.py 001")
        sys.exit(1)
    
    migration_num = sys.argv[1]
    migration_file = MIGRATIONS_DIR / f"{migration_num}_initial_schema.sql"
    
    if not migration_file.exists():
        print(f"ERROR: Migration file not found: {migration_file}")
        sys.exit(1)
    
    success = apply_migration(migration_file)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
