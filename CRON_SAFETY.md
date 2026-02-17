# Cron Safety Protocol

## Issue
Cron jobs skip silently if HEARTBEAT.md is empty, even for critical trading operations.

## Fix Applied
1. HEARTBEAT.md now contains paper trading monitoring tasks
2. Cron will execute as scheduled tonight (23:30 AEST)

## Backup Safety
If HEARTBEAT.md is ever empty again:
- Paper trading cron MUST alert Discord before skipping
- Run in safe mode (1 test trade per wallet) rather than skipping entirely

## Alert Rule
```
IF heartbeat_empty AND job_id == "paper-trading-startup-2330":
  POST to Discord: "⚠️ Paper trading start blocked by empty HEARTBEAT.md - running safe mode"
  EXECUTE: minimal test trades (1 per wallet)
```

## Owner
Tyler expects paper trading to START at 23:30 AEST every day, regardless of heartbeat status.
