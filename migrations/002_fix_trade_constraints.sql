-- Migration 002: Fix trade constraints for decimal precision
-- Created: 2026-02-17
-- Description: Relax valid_gross_amount constraint to allow small rounding differences

ALTER TABLE trades
DROP CONSTRAINT IF EXISTS valid_gross_amount;

ALTER TABLE trades
DROP CONSTRAINT IF EXISTS valid_net_amount;

-- Allow small precision differences (< 1 cent)
ALTER TABLE trades
ADD CONSTRAINT valid_gross_amount CHECK (
    ABS(gross_amount - (quantity * fill_price)) < 0.01
);

ALTER TABLE trades
ADD CONSTRAINT valid_net_amount CHECK (
    (side = 'BUY' AND net_amount >= gross_amount - 0.01)
    OR (side = 'SELL' AND net_amount <= gross_amount + 0.01)
);
