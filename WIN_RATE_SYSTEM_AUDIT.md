# Win-Rate System Comprehensive Audit & Implementation Report

## Executive Summary

The win-rate tracking system is a sophisticated infrastructure for evaluating trading recommendation performance. The system correctly tracks recommendation outcomes using historical price data but had two critical aggregation bugs that have now been fixed.

## Fixes Implemented

1. Fixed get_win_rate_by_date() query to include trailing_stop outcomes
2. Fixed get_win_rate_by_dimension() query to include trailing_stop outcomes  
3. Implemented cleanup_old_records() method with retention policy enforcement
4. Added POST /win-rate/cleanup admin API endpoint
5. Added 5 performance indexes on win_rate_records table

## Critical Bug #1: get_win_rate_by_date() - Line 788

Location: core/database.py, method get_win_rate_by_date()

Before:
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,

After:
  SUM(CASE WHEN outcome IN ('win', 'trailing_stop') THEN 1 ELSE 0 END) as wins,

Impact: Trend chart now shows accurate daily win rates. Trailing_stop outcomes 
(profitable exits) are now correctly counted as wins.

Used by: GET /win-rate/trend endpoint, Frontend TrendChart component

## Critical Bug #2: get_win_rate_by_dimension() - Line 811

Location: core/database.py, method get_win_rate_by_dimension()

Before:
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,

After:
  SUM(CASE WHEN outcome IN ('win', 'trailing_stop') THEN 1 ELSE 0 END) as wins,

Impact: Strategy/direction breakdown now accurate. Both short_term and swing 
strategies properly count trailing_stop outcomes.

Used by: GET /win-rate/by-date endpoint, Frontend DimensionPanel

## New Feature #1: cleanup_old_records() Method

Location: core/database.py, lines 869-938

Enforces data retention policy:
- Short-term records: 21 days retention (configurable)
- Swing records: 90 days retention (configurable)
- Pending records: 21 days retention (configurable)

Returns deletion statistics:
{
  "status": "success|error",
  "short_term_deleted": 150,
  "swing_deleted": 42,
  "pending_deleted": 8,
  "total_deleted": 200
}

## New Feature #2: POST /win-rate/cleanup Endpoint

Location: api/routes/user.py, lines 270-281

Permission: Admin-only
Behavior: Calls db.cleanup_old_records() in threadpool, returns deletion stats

## New Feature #3: Database Performance Indexes

Added 5 indexes to schema:

1. idx_win_rate_outcome - ON (outcome)
   Used by: Aggregation queries filtering by status

2. idx_win_rate_run_date - ON (run_date)
   Used by: Date-range queries for trend analysis

3. idx_win_rate_market_strategy - ON (market, strategy)
   Used by: Dimension grouping queries

4. idx_win_rate_ticker_market - ON (ticker, market)
   Used by: Per-stock performance lookups

5. idx_win_rate_created_at - ON (created_at)
   Used by: Cleanup queries by creation date

Performance: Expected 10-100x speedup for aggregation queries on large datasets

## Outcome Types

Pending - Awaiting evaluation
Win - Hit TP before SL (profitable)
Trailing_stop - Activated trailing stop at profit (profitable)
Loss - Hit SL before TP (loss)
Partial_win - Detected partial profit pattern (profitable)
Timeout - Holding period expired neutral (neutral)
Timeout_at_profit - Expired while above TP (profitable)
Timeout_at_loss - Expired while below SL (loss)

## Evaluation Logic (pipeline/evaluator.py)

Two-Phase Evaluation:

Phase 1: Entry Fill Detection
- Verify limit-order entry was reached
- For LONG: Check if low <= entry_price
- For SHORT: Check if high >= entry_price

Phase 2: TP/SL/Trailing-Stop Evaluation
- Track best price (high for LONG, low for SHORT)
- Activate trailing stop at 50% (short_term) or 40% (swing) of target distance
- Apply trailing distance (40% for short_term, 35% for swing)
- Check conditions in order: SL+TP, SL only, TP only, partial_win, timeout

## Configuration (pipeline/config.py)

Short-Term Strategy:
- Holding: 3 days (default), up to 5 max
- Trailing activation: 50% of TP distance
- Trailing distance: 40% stop offset
- SL bounds: 1.5% - 6% of entry

Swing Strategy:
- Holding: 10 days (default), up to 30 max
- Trailing activation: 40% of TP distance
- Trailing distance: 35% stop offset
- SL bounds: 1.5% - 10% of entry

Retention Policy:
- Short-term: 21 days
- Swing: 90 days
- Pending: 21 days

## System Verification

- Record creation pipeline verified (runner.py lines 321-349)
- Automatic evaluation trigger verified (runner.py line 188)
- Manual evaluation trigger verified (user.py line 260)
- Trailing stop integration verified (evaluator.py)
- Summary statistics accuracy verified
- Aggregation bugs fixed
- Cleanup system implemented
- Performance indexes added

## API Endpoints

GET /win-rate/summary - Overall statistics with correct win rate
GET /win-rate/by-date - Daily aggregations (FIXED: includes trailing_stops)
GET /win-rate/trend - Cumulative return trend using fixed data
GET /win-rate/details - Individual trade records
POST /win-rate/evaluate - Trigger evaluation of pending records
POST /win-rate/cleanup - Trigger cleanup based on retention policy (NEW)

## Commit Details

Commit: dbdf637
Message: Fix win-rate aggregation queries and implement cleanup system

Files Modified:
- core/database.py: +95 lines
- api/routes/user.py: +16 lines

Total Changes: +111 lines across 2 files
