"""SQLite storage for analysis reports and dashboard statistics.

Privacy: the raw message is never stored, only its SHA-256 hash plus the
extracted scam indicators (links, phone numbers) needed for trend analysis.
"""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from app.models import CATEGORY_THAI_LABELS, HIGH_RISK_THRESHOLD, AnalysisResult, ScamCategory

Period = Literal["day", "week", "month"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_code TEXT NOT NULL UNIQUE,
    text_hash TEXT NOT NULL,
    category TEXT NOT NULL,
    risk INTEGER NOT NULL,
    impersonated_org TEXT,
    entities_json TEXT NOT NULL,
    engine TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    red_flags_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
"""
# Columns added after the first release; created on older databases at startup.
LATER_COLUMNS = {
    "summary": "TEXT NOT NULL DEFAULT ''",
    "red_flags_json": "TEXT NOT NULL DEFAULT '[]'",
}

REPORT_PREFIX = "SA"
# Buckets are computed in Thailand time so "today" matches what users expect.
LOCAL_TIME_OFFSET = "+7 hours"
PERIOD_FORMATS: dict[str, str] = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}
PERIOD_WINDOWS: dict[str, timedelta] = {
    "day": timedelta(days=30),
    "week": timedelta(weeks=12),
    "month": timedelta(days=365),
}
TOP_ORG_LIMIT = 8
RECENT_LIMIT = 10
EMERGING_WINDOW = timedelta(hours=24)
EMERGING_MIN_COUNT = 2


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


class ReportRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
            for name, definition in LATER_COLUMNS.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, result: AnalysisResult, text: str, source: str,
             created_at: datetime | None = None) -> str:
        moment = created_at or datetime.now(timezone.utc)
        entities = result.entities.to_dict() | {"hosts": [f.host for f in result.domain_findings]}
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                code = self._next_code(conn, moment.year)
                conn.execute(
                    "INSERT INTO reports (report_code, text_hash, category, risk, impersonated_org,"
                    " entities_json, engine, source, created_at, summary, red_flags_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, hash_text(text), result.category.value, result.risk,
                     result.impersonated_org, json.dumps(entities, ensure_ascii=False),
                     result.engine, source, _iso(moment), result.summary,
                     json.dumps(list(result.red_flags), ensure_ascii=False)),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return code

    @staticmethod
    def _next_code(conn: sqlite3.Connection, year: int) -> str:
        prefix = f"{REPORT_PREFIX}-{year}-"
        row = conn.execute(
            "SELECT MAX(CAST(substr(report_code, ?) AS INTEGER)) FROM reports WHERE report_code LIKE ?",
            (len(prefix) + 1, prefix + "%"),
        ).fetchone()
        return f"{prefix}{(row[0] or 0) + 1:04d}"

    def get(self, report_code: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT report_code, category, risk, impersonated_org, entities_json, summary,"
                " red_flags_json, created_at FROM reports WHERE report_code = ?",
                (report_code,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["entities"] = json.loads(record.pop("entities_json"))
        record["red_flags"] = json.loads(record.pop("red_flags_json"))
        return record

    def count(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

    def clear(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM reports")

    def stats(self, period: Period = "day", now: datetime | None = None) -> dict:
        if period not in PERIOD_FORMATS:
            raise ValueError(f"unsupported period: {period}")
        now = now or datetime.now(timezone.utc)
        since = _iso(now - PERIOD_WINDOWS[period])
        with closing(self._connect()) as conn:
            return {
                "period": period,
                "totals": self._totals(conn, since),
                "by_category": self._by_category(conn, since),
                "by_org": self._by_org(conn, since),
                "trend": self._trend(conn, since, PERIOD_FORMATS[period]),
                "emerging_domains": self._emerging_domains(conn, _iso(now - EMERGING_WINDOW)),
                "recent": self._recent(conn),
            }

    @staticmethod
    def _totals(conn: sqlite3.Connection, since: str) -> dict:
        row = conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN category != ? THEN 1 ELSE 0 END) AS scams,"
            " SUM(CASE WHEN risk >= ? THEN 1 ELSE 0 END) AS high_risk"
            " FROM reports WHERE created_at >= ?",
            (ScamCategory.SAFE.value, HIGH_RISK_THRESHOLD, since),
        ).fetchone()
        return {"total": row["total"], "scams": row["scams"] or 0, "high_risk": row["high_risk"] or 0}

    @staticmethod
    def _by_category(conn: sqlite3.Connection, since: str) -> list[dict]:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM reports WHERE created_at >= ?"
            " GROUP BY category ORDER BY count DESC",
            (since,),
        ).fetchall()
        return [
            {"category": r["category"], "label": CATEGORY_THAI_LABELS[ScamCategory(r["category"])],
             "count": r["count"]}
            for r in rows
        ]

    @staticmethod
    def _by_org(conn: sqlite3.Connection, since: str) -> list[dict]:
        rows = conn.execute(
            "SELECT impersonated_org AS org, COUNT(*) AS count FROM reports"
            " WHERE created_at >= ? AND impersonated_org IS NOT NULL AND category != ?"
            " GROUP BY impersonated_org ORDER BY count DESC LIMIT ?",
            (since, ScamCategory.SAFE.value, TOP_ORG_LIMIT),
        ).fetchall()
        return [{"org": r["org"], "count": r["count"]} for r in rows]

    @staticmethod
    def _trend(conn: sqlite3.Connection, since: str, bucket_format: str) -> list[dict]:
        rows = conn.execute(
            "SELECT strftime(?, created_at, ?) AS bucket, COUNT(*) AS total,"
            " SUM(CASE WHEN category != ? THEN 1 ELSE 0 END) AS scams"
            " FROM reports WHERE created_at >= ? GROUP BY bucket ORDER BY bucket",
            (bucket_format, LOCAL_TIME_OFFSET, ScamCategory.SAFE.value, since),
        ).fetchall()
        return [{"bucket": r["bucket"], "total": r["total"], "scams": r["scams"]} for r in rows]

    @staticmethod
    def _emerging_domains(conn: sqlite3.Connection, since: str) -> list[dict]:
        rows = conn.execute(
            "SELECT host.value AS domain, COUNT(*) AS count"
            " FROM reports, json_each(reports.entities_json, '$.hosts') AS host"
            " WHERE reports.created_at >= ? AND reports.category != ?"
            " GROUP BY host.value HAVING count >= ? ORDER BY count DESC",
            (since, ScamCategory.SAFE.value, EMERGING_MIN_COUNT),
        ).fetchall()
        return [{"domain": r["domain"], "count": r["count"]} for r in rows]

    @staticmethod
    def _recent(conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT report_code, category, risk, impersonated_org, created_at FROM reports"
            " WHERE category != ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (ScamCategory.SAFE.value, RECENT_LIMIT),
        ).fetchall()
        return [dict(r) for r in rows]
