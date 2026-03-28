"""SQLite persistence for recommendations, screening, watchlist, evaluations.

Two database scopes (mirroring astock-quant):
  - system.db  : admin recommendations, published recommendations, win-rate
  - per-user   : screening history, watchlist
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class Database:
    """SQLite storage with dual-table recommendation publishing."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

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

            -- Admin recommendation runs (internal)
            CREATE TABLE IF NOT EXISTS daily_recommendation_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_date        TEXT    NOT NULL UNIQUE,
                market          TEXT    NOT NULL DEFAULT 'all',
                strategy        TEXT    NOT NULL DEFAULT 'dual',
                result_count    INTEGER NOT NULL DEFAULT 0,
                run_status      TEXT    NOT NULL DEFAULT 'published',
                trigger_source  TEXT    DEFAULT 'system_auto',
                trigger_note    TEXT    DEFAULT '',
                source_count    INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                published_count INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_recommendation_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          INTEGER NOT NULL,
                ticker          TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                market          TEXT    NOT NULL,
                strategy        TEXT    NOT NULL DEFAULT 'short_term',
                direction       TEXT    NOT NULL DEFAULT 'buy',
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
                holding_days    INTEGER DEFAULT 5,
                tech_reason     TEXT    DEFAULT '',
                news_reason     TEXT    DEFAULT '',
                fundamental_reason TEXT DEFAULT '',
                llm_reason      TEXT    DEFAULT '',
                valuation_summary TEXT  DEFAULT '',
                quality_score   REAL,
                safety_margin   REAL,
                risk_flags      TEXT    DEFAULT '[]',
                price           REAL    DEFAULT 0,
                change_pct      REAL    DEFAULT 0,
                FOREIGN KEY (run_id) REFERENCES daily_recommendation_runs(id)
            );

            -- Published recommendation runs (user-visible)
            CREATE TABLE IF NOT EXISTS published_recommendation_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_date        TEXT    NOT NULL UNIQUE,
                market          TEXT    NOT NULL DEFAULT 'all',
                strategy        TEXT    NOT NULL DEFAULT 'dual',
                result_count    INTEGER NOT NULL DEFAULT 0,
                run_status      TEXT    NOT NULL DEFAULT 'published',
                trigger_source  TEXT    DEFAULT 'system_auto',
                trigger_note    TEXT    DEFAULT '',
                published_count INTEGER NOT NULL DEFAULT 0,
                published_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS published_recommendation_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          INTEGER NOT NULL,
                ticker          TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                market          TEXT    NOT NULL,
                strategy        TEXT    NOT NULL DEFAULT 'short_term',
                direction       TEXT    NOT NULL DEFAULT 'buy',
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
                holding_days    INTEGER DEFAULT 5,
                tech_reason     TEXT    DEFAULT '',
                news_reason     TEXT    DEFAULT '',
                fundamental_reason TEXT DEFAULT '',
                llm_reason      TEXT    DEFAULT '',
                valuation_summary TEXT  DEFAULT '',
                quality_score   REAL,
                safety_margin   REAL,
                risk_flags      TEXT    DEFAULT '[]',
                price           REAL    DEFAULT 0,
                change_pct      REAL    DEFAULT 0,
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
            "(SELECT id FROM daily_recommendation_runs WHERE ref_date=?)",
            (ref_date,),
        )
        self._conn.execute(
            "DELETE FROM daily_recommendation_runs WHERE ref_date=?", (ref_date,)
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

    def get_daily_recommendations(self, ref_date: str):
        run = self._conn.execute(
            "SELECT * FROM daily_recommendation_runs WHERE ref_date=?", (ref_date,)
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

    def publish_recommendations(self, ref_date: str, admin_run: dict,
                                admin_items: list[dict]) -> int:
        self._conn.execute(
            "DELETE FROM published_recommendation_items WHERE run_id IN "
            "(SELECT id FROM published_recommendation_runs WHERE ref_date=?)",
            (ref_date,),
        )
        self._conn.execute(
            "DELETE FROM published_recommendation_runs WHERE ref_date=?", (ref_date,)
        )

        cur = self._conn.execute(
            """INSERT INTO published_recommendation_runs
               (ref_date, market, strategy, result_count, run_status,
                trigger_source, trigger_note, published_count)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ref_date, admin_run.get("market", "all"),
             admin_run.get("strategy", "dual"), len(admin_items),
             "published", admin_run.get("trigger_source", "system_auto"),
             admin_run.get("trigger_note", ""), len(admin_items)),
        )
        run_id = cur.lastrowid
        self._insert_recommendation_items("published_recommendation_items", run_id, admin_items)
        self._conn.commit()
        logger.info(f"已发布 {len(admin_items)} 条推荐 ({ref_date})")
        return run_id

    def get_published_recommendations(self, ref_date: str):
        run = self._conn.execute(
            "SELECT * FROM published_recommendation_runs WHERE ref_date=?",
            (ref_date,),
        ).fetchone()
        if not run:
            return None, []
        items = self._conn.execute(
            "SELECT * FROM published_recommendation_items WHERE run_id=? ORDER BY combined_score DESC",
            (run["id"],),
        ).fetchall()
        return dict(run), [dict(i) for i in items]

    def get_latest_published(self):
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

    def list_published_runs(self, limit: int = 20) -> pd.DataFrame:
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
                entry_price, stop_loss, take_profit, holding_days, outcome)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (record["run_date"], record["ticker"], record["name"],
             record["market"], record["strategy"], record["direction"],
             record["entry_price"], record["stop_loss"], record["take_profit"],
             record["holding_days"], "pending"),
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
                             days: int = 90) -> dict:
        where = "WHERE outcome != 'pending'"
        params: list = []
        if market:
            where += " AND market = ?"
            params.append(market)

        rows = self._conn.execute(
            f"SELECT outcome, COUNT(*) as cnt, AVG(return_pct) as avg_ret "
            f"FROM win_rate_records {where} GROUP BY outcome",
            params,
        ).fetchall()

        total = sum(r["cnt"] for r in rows)
        wins = sum(r["cnt"] for r in rows if r["outcome"] in ("win", "partial"))
        losses = sum(r["cnt"] for r in rows if r["outcome"] == "loss")
        avg_return = 0.0
        if rows:
            avg_return = sum(r["avg_ret"] * r["cnt"] for r in rows) / max(total, 1)

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(total, 1) * 100, 1),
            "avg_return": round(avg_return, 2),
        }

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
            self._conn.execute(
                f"""INSERT INTO {table}
                    (run_id, ticker, name, market, strategy, direction, score,
                     confidence, tech_score, news_score, fundamental_score,
                     combined_score, entry_price, entry_2, stop_loss,
                     take_profit, take_profit_2, holding_days,
                     tech_reason, news_reason, fundamental_reason,
                     llm_reason, valuation_summary, quality_score,
                     safety_margin, risk_flags, price, change_pct)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, item.get("ticker", ""), item.get("name", ""),
                 item.get("market", ""), item.get("strategy", "short_term"),
                 item.get("direction", "buy"), item.get("score", 0),
                 item.get("confidence", 0), item.get("tech_score", 0),
                 item.get("news_score", 0), item.get("fundamental_score", 0),
                 item.get("combined_score", 0), item.get("entry_price", 0),
                 item.get("entry_2", 0), item.get("stop_loss", 0),
                 item.get("take_profit", 0), item.get("take_profit_2", 0),
                 item.get("holding_days", 5), item.get("tech_reason", ""),
                 item.get("news_reason", ""), item.get("fundamental_reason", ""),
                 item.get("llm_reason", ""), item.get("valuation_summary", ""),
                 item.get("quality_score"), item.get("safety_margin"),
                 risk_flags, item.get("price", 0), item.get("change_pct", 0)),
            )
