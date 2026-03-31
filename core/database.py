"""SQLite persistence for recommendations, screening, watchlist, evaluations.

Two database scopes:
  - system.db  : admin recommendations, published recommendations, win-rate
  - per-user   : screening history, watchlist

All recommendation tables are market-scoped: US and HK pipelines
store and query independently via (ref_date, market) composite keys.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class Database:
    """SQLite storage with market-isolated recommendation publishing."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        self._migrate_add_columns()
        self._migrate_market_isolation()
        self._migrate_win_rate_scores()
        self._migrate_recommendation_extra_cols()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_tables(self):
        self._conn.executescript("""
            -- Screening runs (per-user)
            CREATE TABLE IF NOT EXISTS screening_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                market          TEXT    NOT NULL,
                ref_date        TEXT    NOT NULL,
                top_n           INTEGER NOT NULL,
                result_count    INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS screening_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER NOT NULL,
                ticker      TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                market      TEXT    NOT NULL,
                score       REAL    NOT NULL,
                price       REAL    DEFAULT 0,
                change_pct  REAL    DEFAULT 0,
                volume      REAL    DEFAULT 0,
                market_cap  REAL    DEFAULT 0,
                pe_ttm      REAL,
                pb          REAL,
                factors     TEXT    DEFAULT '{}',
                FOREIGN KEY (run_id) REFERENCES screening_runs(id)
            );

            -- Admin recommendation runs (internal, market-isolated)
            CREATE TABLE IF NOT EXISTS daily_recommendation_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_date        TEXT    NOT NULL,
                market          TEXT    NOT NULL DEFAULT 'us_stock',
                strategy        TEXT    NOT NULL DEFAULT 'dual',
                result_count    INTEGER NOT NULL DEFAULT 0,
                run_status      TEXT    NOT NULL DEFAULT 'published',
                trigger_source  TEXT    DEFAULT 'system_auto',
                trigger_note    TEXT    DEFAULT '',
                source_count    INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                published_count INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ref_date, market)
            );

            CREATE TABLE IF NOT EXISTS daily_recommendation_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          INTEGER NOT NULL,
                ticker          TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                market          TEXT    NOT NULL,
                strategy        TEXT    NOT NULL DEFAULT 'short_term',
                direction       TEXT    NOT NULL DEFAULT 'buy',
                action          TEXT    DEFAULT 'hold',
                score           REAL    NOT NULL,
                confidence      INTEGER DEFAULT 0,
                tech_score      INTEGER DEFAULT 0,
                news_score      INTEGER DEFAULT 0,
                fundamental_score INTEGER DEFAULT 0,
                combined_score  INTEGER DEFAULT 0,
                entry_price     REAL    DEFAULT 0,
                entry_2         REAL    DEFAULT 0,
                stop_loss       REAL    DEFAULT 0,
                take_profit     REAL    DEFAULT 0,
                take_profit_2   REAL    DEFAULT 0,
                take_profit_3   REAL    DEFAULT 0,
                holding_days    INTEGER DEFAULT 5,
                tech_reason     TEXT    DEFAULT '',
                news_reason     TEXT    DEFAULT '',
                fundamental_reason TEXT DEFAULT '',
                llm_reason      TEXT    DEFAULT '',
                recommendation_reason TEXT DEFAULT '',
                valuation_summary TEXT  DEFAULT '',
                quality_score   REAL,
                safety_margin   REAL,
                risk_flags      TEXT    DEFAULT '[]',
                risk_note       TEXT    DEFAULT '',
                position_note   TEXT    DEFAULT '',
                themes          TEXT    DEFAULT '[]',
                price           REAL    DEFAULT 0,
                change_pct      REAL    DEFAULT 0,
                FOREIGN KEY (run_id) REFERENCES daily_recommendation_runs(id)
            );

            -- Published recommendation runs (user-visible, market-isolated)
            CREATE TABLE IF NOT EXISTS published_recommendation_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_date        TEXT    NOT NULL,
                market          TEXT    NOT NULL DEFAULT 'us_stock',
                strategy        TEXT    NOT NULL DEFAULT 'dual',
                result_count    INTEGER NOT NULL DEFAULT 0,
                run_status      TEXT    NOT NULL DEFAULT 'published',
                trigger_source  TEXT    DEFAULT 'system_auto',
                trigger_note    TEXT    DEFAULT '',
                published_count INTEGER NOT NULL DEFAULT 0,
                published_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ref_date, market)
            );

            CREATE TABLE IF NOT EXISTS published_recommendation_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          INTEGER NOT NULL,
                ticker          TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                market          TEXT    NOT NULL,
                strategy        TEXT    NOT NULL DEFAULT 'short_term',
                direction       TEXT    NOT NULL DEFAULT 'buy',
                action          TEXT    DEFAULT 'hold',
                score           REAL    NOT NULL,
                confidence      INTEGER DEFAULT 0,
                tech_score      INTEGER DEFAULT 0,
                news_score      INTEGER DEFAULT 0,
                fundamental_score INTEGER DEFAULT 0,
                combined_score  INTEGER DEFAULT 0,
                entry_price     REAL    DEFAULT 0,
                entry_2         REAL    DEFAULT 0,
                stop_loss       REAL    DEFAULT 0,
                take_profit     REAL    DEFAULT 0,
                take_profit_2   REAL    DEFAULT 0,
                take_profit_3   REAL    DEFAULT 0,
                holding_days    INTEGER DEFAULT 5,
                tech_reason     TEXT    DEFAULT '',
                news_reason     TEXT    DEFAULT '',
                fundamental_reason TEXT DEFAULT '',
                llm_reason      TEXT    DEFAULT '',
                recommendation_reason TEXT DEFAULT '',
                valuation_summary TEXT  DEFAULT '',
                quality_score   REAL,
                safety_margin   REAL,
                risk_flags      TEXT    DEFAULT '[]',
                risk_note       TEXT    DEFAULT '',
                position_note   TEXT    DEFAULT '',
                themes          TEXT    DEFAULT '[]',
                price           REAL    DEFAULT 0,
                change_pct      REAL    DEFAULT 0,
                sector          TEXT    DEFAULT '',
                position_pct    INTEGER DEFAULT 5,
                earnings_days_away INTEGER,
                earnings_date_str TEXT   DEFAULT '',
                show_trading_params INTEGER DEFAULT 0,
                rsi             REAL,
                macd_histogram  REAL,
                bollinger_position REAL,
                obv_trend       TEXT    DEFAULT '',
                options_signal  TEXT    DEFAULT '',
                options_pc_ratio REAL,
                options_unusual_activity INTEGER DEFAULT 0,
                insider_signal  TEXT    DEFAULT '',
                FOREIGN KEY (run_id) REFERENCES published_recommendation_runs(id)
            );

            -- Win-rate tracking
            CREATE TABLE IF NOT EXISTS win_rate_records (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date        TEXT    NOT NULL,
                ticker          TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                market          TEXT    NOT NULL,
                strategy        TEXT    NOT NULL,
                direction       TEXT    NOT NULL,
                entry_price     REAL    NOT NULL,
                stop_loss       REAL    NOT NULL,
                take_profit     REAL    NOT NULL,
                holding_days    INTEGER NOT NULL,
                outcome         TEXT    DEFAULT 'pending',
                exit_price      REAL,
                return_pct      REAL,
                evaluated_at    TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Daily stock evaluations cache
            CREATE TABLE IF NOT EXISTS daily_stock_evaluations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date    TEXT    NOT NULL,
                ticker      TEXT    NOT NULL,
                market      TEXT    NOT NULL,
                evaluation  TEXT    NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_date, ticker, market)
            );

            -- Deep analysis cache
            CREATE TABLE IF NOT EXISTS deep_analysis_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                market      TEXT    NOT NULL,
                data        TEXT    NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, market)
            );

            -- Market sentiment cache (computed during pipeline run)
            CREATE TABLE IF NOT EXISTS market_sentiment_cache (
                market      TEXT    PRIMARY KEY,
                data        TEXT    NOT NULL,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Watchlist (per-user db)
            CREATE TABLE IF NOT EXISTS watchlist_items (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker                  TEXT    NOT NULL,
                name                    TEXT    NOT NULL,
                market                  TEXT    NOT NULL,
                recommendation_item_id  INTEGER,
                note                    TEXT    DEFAULT '',
                is_active               BOOLEAN DEFAULT 1,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, market)
            );
        """)
        self._conn.commit()

    def _migrate_add_columns(self):
        """Add missing columns to existing recommendation tables."""
        new_cols = [
            ("take_profit_3", "REAL DEFAULT 0"),
            ("action", "TEXT DEFAULT 'hold'"),
            ("recommendation_reason", "TEXT DEFAULT ''"),
            ("risk_note", "TEXT DEFAULT ''"),
            ("position_note", "TEXT DEFAULT ''"),
            ("themes", "TEXT DEFAULT '[]'"),
        ]
        for table in ("daily_recommendation_items", "published_recommendation_items"):
            existing = {
                row[1] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for col_name, col_def in new_cols:
                if col_name not in existing:
                    try:
                        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                        logger.info(f"Added column {col_name} to {table}")
                    except Exception as e:
                        logger.debug(f"Column {col_name} on {table}: {e}")
            self._conn.commit()

    def _migrate_market_isolation(self):
        """Migrate old single-column UNIQUE(ref_date) to UNIQUE(ref_date, market)."""
        for table in ("daily_recommendation_runs", "published_recommendation_runs"):
            try:
                idx_list = self._conn.execute(
                    f"PRAGMA index_list({table})"
                ).fetchall()
                needs_migration = False
                for idx in idx_list:
                    idx_info = self._conn.execute(
                        f"PRAGMA index_info('{idx['name']}')"
                    ).fetchall()
                    if len(idx_info) == 1 and idx_info[0]["name"] == "ref_date" and idx["unique"]:
                        needs_migration = True
                        break

                if not needs_migration:
                    continue

                logger.info(f"Migrating {table}: UNIQUE(ref_date) -> UNIQUE(ref_date, market)")
                items_table = table.replace("_runs", "_items")

                rows = [dict(r) for r in self._conn.execute(f"SELECT * FROM {table}").fetchall()]
                item_rows = [dict(r) for r in self._conn.execute(f"SELECT * FROM {items_table}").fetchall()]

                self._conn.execute(f"DROP TABLE IF EXISTS {items_table}")
                self._conn.execute(f"DROP TABLE IF EXISTS {table}")
                self._conn.commit()
                self._init_tables()

                for rd in rows:
                    mkt = rd.get("market", "us_stock")
                    if mkt == "all":
                        mkt = "us_stock"
                    try:
                        self._conn.execute(
                            f"INSERT INTO {table} "
                            f"(ref_date, market, strategy, result_count, run_status, "
                            f"trigger_source, trigger_note, source_count, candidate_count, published_count) "
                            f"VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (rd["ref_date"], mkt, rd.get("strategy", "dual"),
                             rd.get("result_count", 0), rd.get("run_status", "published"),
                             rd.get("trigger_source", ""), rd.get("trigger_note", ""),
                             rd.get("source_count", 0), rd.get("candidate_count", 0),
                             rd.get("published_count", 0)),
                        )
                    except sqlite3.IntegrityError:
                        pass

                for ird in item_rows:
                    try:
                        self._insert_recommendation_items(items_table, ird.get("run_id"), [ird])
                    except Exception:
                        pass

                self._conn.commit()
                logger.info(f"Migration complete for {table}")
            except Exception as e:
                logger.warning(f"Migration check for {table}: {e}")

    def _migrate_win_rate_scores(self):
        """Add score/sector columns to win_rate_records for existing databases."""
        table = "win_rate_records"
        new_cols = [
            ("news_score", "INTEGER DEFAULT 0"),
            ("tech_score", "INTEGER DEFAULT 0"),
            ("fundamental_score", "INTEGER DEFAULT 0"),
            ("combined_score", "INTEGER DEFAULT 0"),
            ("confidence", "INTEGER DEFAULT 0"),
            ("sector", "TEXT DEFAULT ''"),
        ]
        try:
            existing = {
                row[1] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for col_name, col_def in new_cols:
                if col_name not in existing:
                    try:
                        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                        logger.info(f"Added column {col_name} to {table}")
                    except Exception as e:
                        logger.debug(f"Column {col_name} on {table}: {e}")
            self._conn.commit()
        except Exception as e:
            logger.warning(f"win_rate_records migration: {e}")

    def _migrate_recommendation_extra_cols(self):
        """Add indicator/signal columns to recommendation items tables."""
        new_cols = [
            ("sector", "TEXT DEFAULT ''"),
            ("position_pct", "INTEGER DEFAULT 5"),
            ("earnings_days_away", "INTEGER"),
            ("earnings_date_str", "TEXT DEFAULT ''"),
            ("show_trading_params", "INTEGER DEFAULT 0"),
            ("rsi", "REAL"),
            ("macd_histogram", "REAL"),
            ("bollinger_position", "REAL"),
            ("obv_trend", "TEXT DEFAULT ''"),
            ("options_signal", "TEXT DEFAULT ''"),
            ("options_pc_ratio", "REAL"),
            ("options_unusual_activity", "INTEGER DEFAULT 0"),
            ("insider_signal", "TEXT DEFAULT ''"),
        ]
        for table in ("published_recommendation_items", "daily_recommendation_items"):
            try:
                existing = {
                    row[1] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for col_name, col_def in new_cols:
                    if col_name not in existing:
                        try:
                            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                        except Exception:
                            pass
                self._conn.commit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Screening
    # ------------------------------------------------------------------

    def save_screening_run(self, market: str, ref_date: str, top_n: int,
                           results: list[dict]) -> int:
        cur = self._conn.execute(
            "INSERT INTO screening_runs (market, ref_date, top_n, result_count) VALUES (?,?,?,?)",
            (market, ref_date, top_n, len(results)),
        )
        run_id = cur.lastrowid
        for r in results:
            self._conn.execute(
                """INSERT INTO screening_results
                   (run_id, ticker, name, market, score, price, change_pct,
                    volume, market_cap, pe_ttm, pb, factors)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, r["ticker"], r["name"], r["market"], r["score"],
                 r.get("price", 0), r.get("change_pct", 0), r.get("volume", 0),
                 r.get("market_cap", 0), r.get("pe_ttm"), r.get("pb"),
                 json.dumps(r.get("factors", {}), ensure_ascii=False)),
            )
        self._conn.commit()
        return run_id

    def get_latest_screening(self, market: str | None = None):
        if market:
            run = self._conn.execute(
                "SELECT * FROM screening_runs WHERE market=? ORDER BY id DESC LIMIT 1",
                (market,),
            ).fetchone()
        else:
            run = self._conn.execute(
                "SELECT * FROM screening_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not run:
            return None, pd.DataFrame()
        results = pd.read_sql_query(
            "SELECT * FROM screening_results WHERE run_id=?",
            self._conn, params=(run["id"],),
        )
        return dict(run), results

    def get_screening_runs(self, limit: int = 20) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM screening_runs ORDER BY id DESC LIMIT ?",
            self._conn, params=(limit,),
        )

    # ------------------------------------------------------------------
    # Admin recommendations (daily_recommendation_*)
    # ------------------------------------------------------------------

    def save_daily_recommendation_run(self, ref_date: str, market: str,
                                      items: list[dict], **meta) -> int:
        self._conn.execute(
            "DELETE FROM daily_recommendation_items WHERE run_id IN "
            "(SELECT id FROM daily_recommendation_runs WHERE ref_date=? AND market=?)",
            (ref_date, market),
        )
        self._conn.execute(
            "DELETE FROM daily_recommendation_runs WHERE ref_date=? AND market=?",
            (ref_date, market),
        )

        cur = self._conn.execute(
            """INSERT INTO daily_recommendation_runs
               (ref_date, market, strategy, result_count, source_count,
                candidate_count, published_count, trigger_source, trigger_note)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (ref_date, market, meta.get("strategy", "dual"), len(items),
             meta.get("source_count", 0), meta.get("candidate_count", 0),
             len(items), meta.get("trigger_source", "system_auto"),
             meta.get("trigger_note", "")),
        )
        run_id = cur.lastrowid
        self._insert_recommendation_items("daily_recommendation_items", run_id, items)
        self._conn.commit()
        return run_id

    def get_daily_recommendations(self, ref_date: str, market: str | None = None):
        if market:
            run = self._conn.execute(
                "SELECT * FROM daily_recommendation_runs WHERE ref_date=? AND market=?",
                (ref_date, market),
            ).fetchone()
        else:
            run = self._conn.execute(
                "SELECT * FROM daily_recommendation_runs WHERE ref_date=? ORDER BY id DESC LIMIT 1",
                (ref_date,),
            ).fetchone()
        if not run:
            return None, []
        items = self._conn.execute(
            "SELECT * FROM daily_recommendation_items WHERE run_id=? ORDER BY combined_score DESC",
            (run["id"],),
        ).fetchall()
        return dict(run), [dict(i) for i in items]

    # ------------------------------------------------------------------
    # Published recommendations (published_recommendation_*)
    # ------------------------------------------------------------------

    def publish_recommendations(self, ref_date: str, market: str,
                                admin_run: dict,
                                admin_items: list[dict]) -> int:
        self._conn.execute(
            "DELETE FROM published_recommendation_items WHERE run_id IN "
            "(SELECT id FROM published_recommendation_runs WHERE ref_date=? AND market=?)",
            (ref_date, market),
        )
        self._conn.execute(
            "DELETE FROM published_recommendation_runs WHERE ref_date=? AND market=?",
            (ref_date, market),
        )

        cur = self._conn.execute(
            """INSERT INTO published_recommendation_runs
               (ref_date, market, strategy, result_count, run_status,
                trigger_source, trigger_note, published_count)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ref_date, market,
             admin_run.get("strategy", "dual"), len(admin_items),
             "published", admin_run.get("trigger_source", "system_auto"),
             admin_run.get("trigger_note", ""), len(admin_items)),
        )
        run_id = cur.lastrowid
        self._insert_recommendation_items("published_recommendation_items", run_id, admin_items)
        self._conn.commit()
        logger.info(f"Published {len(admin_items)} recommendations ({ref_date}, {market})")
        return run_id

    def get_published_recommendations(self, ref_date: str, market: str | None = None):
        if market:
            run = self._conn.execute(
                "SELECT * FROM published_recommendation_runs WHERE ref_date=? AND market=?",
                (ref_date, market),
            ).fetchone()
        else:
            run = self._conn.execute(
                "SELECT * FROM published_recommendation_runs WHERE ref_date=? ORDER BY id DESC LIMIT 1",
                (ref_date,),
            ).fetchone()
        if not run:
            return None, []
        items = self._conn.execute(
            "SELECT * FROM published_recommendation_items WHERE run_id=? ORDER BY combined_score DESC",
            (run["id"],),
        ).fetchall()
        return dict(run), [dict(i) for i in items]

    def get_latest_published(self, market: str | None = None):
        if market:
            run = self._conn.execute(
                "SELECT * FROM published_recommendation_runs WHERE market=? ORDER BY ref_date DESC LIMIT 1",
                (market,),
            ).fetchone()
        else:
            run = self._conn.execute(
                "SELECT * FROM published_recommendation_runs ORDER BY ref_date DESC LIMIT 1"
            ).fetchone()
        if not run:
            return None, []
        items = self._conn.execute(
            "SELECT * FROM published_recommendation_items WHERE run_id=? ORDER BY combined_score DESC",
            (run["id"],),
        ).fetchall()
        return dict(run), [dict(i) for i in items]

    def list_published_runs(self, limit: int = 20, market: str | None = None) -> pd.DataFrame:
        if market:
            return pd.read_sql_query(
                "SELECT * FROM published_recommendation_runs WHERE market=? ORDER BY ref_date DESC LIMIT ?",
                self._conn, params=(market, limit),
            )
        return pd.read_sql_query(
            "SELECT * FROM published_recommendation_runs ORDER BY ref_date DESC LIMIT ?",
            self._conn, params=(limit,),
        )
    # ------------------------------------------------------------------
    # Win-rate
    # ------------------------------------------------------------------

    def save_win_rate_record(self, record: dict):
        self._conn.execute(
            """INSERT INTO win_rate_records
               (run_date, ticker, name, market, strategy, direction,
                entry_price, stop_loss, take_profit, holding_days, outcome,
                news_score, tech_score, fundamental_score, combined_score,
                confidence, sector)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record["run_date"], record["ticker"], record["name"],
             record["market"], record["strategy"], record["direction"],
             record["entry_price"], record["stop_loss"], record["take_profit"],
             record["holding_days"], "pending",
             int(record.get("news_score", 0)),
             int(record.get("tech_score", 0)),
             int(record.get("fundamental_score", 0)),
             int(record.get("combined_score", 0)),
             int(record.get("confidence", 0)),
             str(record.get("sector", ""))),
        )
        self._conn.commit()

    def get_pending_evaluations(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM win_rate_records WHERE outcome = 'pending'"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_win_rate(self, record_id: int, outcome: str, exit_price: float,
                        return_pct: float):
        self._conn.execute(
            """UPDATE win_rate_records
               SET outcome=?, exit_price=?, return_pct=?, evaluated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (outcome, exit_price, return_pct, record_id),
        )
        self._conn.commit()

    def get_win_rate_summary(self, market: str | None = None,
                             days: int | None = None) -> dict:
        where_parts = ["outcome != 'pending'"]
        params: list = []
        if market:
            where_parts.append("market = ?")
            params.append(market)
        if days:
            where_parts.append("run_date >= ?")
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(where_parts)

        rows = self._conn.execute(
            f"SELECT outcome, COUNT(*) as cnt, AVG(return_pct) as avg_ret "
            f"FROM win_rate_records {where} GROUP BY outcome",
            params,
        ).fetchall()

        total = sum(r["cnt"] for r in rows)
        wins = sum(r["cnt"] for r in rows if r["outcome"] in ("win", "partial", "partial_win"))
        losses = sum(r["cnt"] for r in rows if r["outcome"] == "loss")
        timeouts = sum(r["cnt"] for r in rows if r["outcome"] == "timeout")
        avg_return = 0.0
        avg_win_return = 0.0
        avg_loss_return = 0.0
        if rows:
            avg_return = sum((r["avg_ret"] or 0) * r["cnt"] for r in rows) / max(total, 1)
        win_rows = [r for r in rows if r["outcome"] in ("win", "partial", "partial_win")]
        loss_rows = [r for r in rows if r["outcome"] == "loss"]
        if win_rows:
            avg_win_return = sum((r["avg_ret"] or 0) * r["cnt"] for r in win_rows) / max(wins, 1)
        if loss_rows:
            avg_loss_return = sum((r["avg_ret"] or 0) * r["cnt"] for r in loss_rows) / max(losses, 1)

        pending_cnt = self._conn.execute(
            "SELECT COUNT(*) FROM win_rate_records WHERE outcome='pending'"
            + (" AND market=?" if market else ""),
            ([market] if market else []),
        ).fetchone()[0]

        return {
            "total_evaluated": total,
            "pending": pending_cnt,
            "wins": wins,
            "losses": losses,
            "timeouts": timeouts,
            "win_rate": round(wins / max(total, 1) * 100, 1),
            "avg_return_pct": round(avg_return, 2),
            "avg_win_return_pct": round(avg_win_return, 2),
            "avg_loss_return_pct": round(avg_loss_return, 2),
        }

    def get_win_rate_details(self, market: str | None = None,
                              limit: int = 50) -> list[dict]:
        where_parts = ["outcome != 'pending'"]
        params: list = []
        if market:
            where_parts.append("market = ?")
            params.append(market)
        where = "WHERE " + " AND ".join(where_parts)
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM win_rate_records {where} ORDER BY evaluated_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_win_rate_by_date(self, market: str | None = None) -> list[dict]:
        """Aggregate win rate by run_date for chart display."""
        where_parts = ["outcome != 'pending'"]
        params: list = []
        if market:
            where_parts.append("market = ?")
            params.append(market)
        where = "WHERE " + " AND ".join(where_parts)
        rows = self._conn.execute(
            f"""SELECT run_date,
                       COUNT(*) as total,
                       SUM(CASE WHEN outcome IN ('win','partial','partial_win') THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                       AVG(return_pct) as avg_return
                FROM win_rate_records {where}
                GROUP BY run_date ORDER BY run_date DESC LIMIT 30""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Deep analysis cache
    # ------------------------------------------------------------------

    def get_deep_cache(self, ticker: str, market: str, ttl_seconds: int = 14400):
        row = self._conn.execute(
            "SELECT * FROM deep_analysis_cache WHERE ticker=? AND market=?",
            (ticker, market),
        ).fetchone()
        if not row:
            return None
        from datetime import datetime, timedelta
        created = datetime.fromisoformat(row["created_at"])
        if (datetime.utcnow() - created).total_seconds() > ttl_seconds:
            return None
        return json.loads(row["data"])

    def save_deep_cache(self, ticker: str, market: str, data: dict):
        self._conn.execute(
            """INSERT INTO deep_analysis_cache (ticker, market, data, created_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(ticker, market) DO UPDATE SET
                 data=excluded.data, created_at=excluded.created_at""",
            (ticker, market, json.dumps(data, ensure_ascii=False, default=str)),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Watchlist (per-user)
    # ------------------------------------------------------------------

    def add_watchlist(self, ticker: str, name: str, market: str,
                      rec_item_id: int | None = None, note: str = "") -> int:
        cur = self._conn.execute(
            """INSERT INTO watchlist_items (ticker, name, market, recommendation_item_id, note)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(ticker, market) DO UPDATE SET
                 is_active=1, note=excluded.note, recommendation_item_id=excluded.recommendation_item_id""",
            (ticker, name, market, rec_item_id, note),
        )
        self._conn.commit()
        return cur.lastrowid

    def remove_watchlist(self, item_id: int):
        self._conn.execute(
            "UPDATE watchlist_items SET is_active=0 WHERE id=?", (item_id,)
        )
        self._conn.commit()

    def list_watchlist(self, active_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM watchlist_items"
        if active_only:
            sql += " WHERE is_active=1"
        sql += " ORDER BY created_at DESC"
        rows = self._conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _insert_recommendation_items(self, table: str, run_id: int,
                                     items: list[dict]):
        for item in items:
            risk_flags = item.get("risk_flags", [])
            if isinstance(risk_flags, list):
                risk_flags = json.dumps(risk_flags, ensure_ascii=False)
            themes = item.get("themes", [])
            if isinstance(themes, list):
                themes = json.dumps(themes, ensure_ascii=False)
            self._conn.execute(
                f"""INSERT INTO {table}
                    (run_id, ticker, name, market, strategy, direction, action,
                     score, confidence, tech_score, news_score, fundamental_score,
                     combined_score, entry_price, entry_2, stop_loss,
                     take_profit, take_profit_2, take_profit_3, holding_days,
                     tech_reason, news_reason, fundamental_reason,
                     llm_reason, recommendation_reason, valuation_summary,
                     quality_score, safety_margin, risk_flags, risk_note,
                     position_note, themes, price, change_pct,
                     sector, position_pct, earnings_days_away, earnings_date_str,
                     show_trading_params, rsi, macd_histogram, bollinger_position,
                     obv_trend, options_signal, options_pc_ratio,
                     options_unusual_activity, insider_signal)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                            ?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, item.get("ticker", ""), item.get("name", ""),
                 item.get("market", ""), item.get("strategy", "short_term"),
                 item.get("direction", "buy"), item.get("action", "hold"),
                 item.get("score", 0),
                 item.get("confidence", 0), item.get("tech_score", 0),
                 item.get("news_score", 0), item.get("fundamental_score", 0),
                 item.get("combined_score", 0), item.get("entry_price", 0),
                 item.get("entry_2", 0), item.get("stop_loss", 0),
                 item.get("take_profit", 0), item.get("take_profit_2", 0),
                 item.get("take_profit_3", 0), item.get("holding_days", 5),
                 item.get("tech_reason", ""), item.get("news_reason", ""),
                 item.get("fundamental_reason", ""),
                 item.get("llm_reason", ""),
                 item.get("recommendation_reason", ""),
                 item.get("valuation_summary", ""),
                 item.get("quality_score"), item.get("safety_margin"),
                 risk_flags, item.get("risk_note", ""),
                 item.get("position_note", ""), themes,
                 item.get("price", 0), item.get("change_pct", 0),
                 item.get("sector", ""),
                 item.get("position_pct", 5),
                 item.get("earnings_days_away"),
                 item.get("earnings_date_str", ""),
                 1 if item.get("show_trading_params") else 0,
                 item.get("rsi"),
                 item.get("macd_histogram"),
                 item.get("bollinger_position"),
                 item.get("obv_trend", ""),
                 item.get("options_signal", ""),
                 item.get("options_pc_ratio"),
                 1 if item.get("options_unusual_activity") else 0,
                 item.get("insider_signal", "")),
            )

    # ------------------------------------------------------------------
    # Market sentiment cache
    # ------------------------------------------------------------------

    def save_market_sentiment(self, market: str, data: dict):
        import json
        self._conn.execute(
            """INSERT INTO market_sentiment_cache (market, data, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(market) DO UPDATE SET data=excluded.data, updated_at=CURRENT_TIMESTAMP""",
            (market, json.dumps(data, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_market_sentiment(self, market: str) -> dict | None:
        import json
        row = self._conn.execute(
            "SELECT data, updated_at FROM market_sentiment_cache WHERE market = ?",
            (market,),
        ).fetchone()
        if not row:
            return None
        result = json.loads(row["data"])
        result["_cached_at"] = row["updated_at"]
        return result
