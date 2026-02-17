-- Migration 001 DOWN: Rollback Initial Paper Trading Schema

DROP VIEW IF EXISTS wallets_equity CASCADE;
DROP VIEW IF EXISTS positions_current CASCADE;

DROP TRIGGER IF EXISTS positions_updated_at ON positions;
DROP TRIGGER IF EXISTS orders_updated_at ON orders;
DROP TRIGGER IF EXISTS wallets_updated_at ON wallets;

DROP FUNCTION IF EXISTS update_updated_at CASCADE;

DROP TABLE IF EXISTS strategy_metrics CASCADE;
DROP TABLE IF EXISTS market_data CASCADE;
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS wallets CASCADE;

DROP TYPE IF EXISTS market_type CASCADE;
DROP TYPE IF EXISTS order_status CASCADE;
DROP TYPE IF EXISTS order_type CASCADE;
DROP TYPE IF EXISTS order_side CASCADE;
