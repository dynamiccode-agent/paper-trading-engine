-- Add wallet_id column to trade_journal (additive only)
ALTER TABLE trade_journal
  ADD COLUMN IF NOT EXISTS wallet_id UUID;

-- Add index
CREATE INDEX IF NOT EXISTS trade_journal_wallet_id_idx
  ON trade_journal (wallet_id);

-- Add FK constraint (safe - allows NULL for existing rows)
ALTER TABLE trade_journal
  ADD CONSTRAINT trade_journal_wallet_fk
  FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE;
