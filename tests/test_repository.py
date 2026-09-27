from datetime import datetime, timedelta, timezone

import pytest

from app.analyzer import ScamAnalyzer
from app.repository import ReportRepository, hash_text

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
PHISHING = "พัสดุตกค้าง กรุณาอัปเดตภายใน 24 ชม. ที่ parcel-th-update.cc"
SAFE = "พรุ่งนี้ประชุม 10 โมงนะ"


@pytest.fixture
def repo(tmp_path):
    return ReportRepository(str(tmp_path / "test.db"))


@pytest.fixture
def analyzer():
    return ScamAnalyzer()


def save(repo, analyzer, text, at=NOW, source="test"):
    return repo.save(analyzer.analyze(text), text, source, created_at=at)


def test_report_codes_are_sequential_per_year(repo, analyzer):
    first = save(repo, analyzer, PHISHING)
    second = save(repo, analyzer, SAFE)
    next_year = save(repo, analyzer, SAFE, at=datetime(2027, 1, 1, tzinfo=timezone.utc))

    assert (first, second, next_year) == ("SA-2026-0001", "SA-2026-0002", "SA-2027-0001")


def test_raw_text_is_not_stored(repo, analyzer, tmp_path):
    save(repo, analyzer, PHISHING)

    raw = (tmp_path / "test.db").read_bytes()

    assert "พัสดุตกค้าง".encode() not in raw
    assert hash_text(PHISHING).encode() in raw


def test_stats_counts_categories_orgs_and_totals(repo, analyzer):
    save(repo, analyzer, PHISHING)
    save(repo, analyzer, PHISHING)
    save(repo, analyzer, SAFE)

    stats = repo.stats("day", now=NOW)

    assert stats["totals"] == {"total": 3, "scams": 2, "high_risk": 2}
    assert stats["by_category"][0] == {"category": "PHISHING", "label": "ลิงก์ปลอม", "count": 2}
    assert stats["by_org"] == [{"org": "ขนส่ง", "count": 2}]
    assert [r["category"] for r in stats["recent"]] == ["PHISHING", "PHISHING"]


def test_emerging_domains_need_repeat_within_24h(repo, analyzer):
    save(repo, analyzer, PHISHING, at=NOW - timedelta(hours=1))
    save(repo, analyzer, PHISHING, at=NOW - timedelta(hours=2))
    save(repo, analyzer, "ยืนยันบัญชีที่ scb-verify.xyz ด่วน", at=NOW - timedelta(hours=1))

    emerging = repo.stats("day", now=NOW)["emerging_domains"]

    assert emerging == [{"domain": "parcel-th-update.cc", "count": 2}]


def test_trend_buckets_use_thai_time(repo, analyzer):
    # 18:00 UTC is 01:00 the next day in Thailand.
    save(repo, analyzer, PHISHING, at=datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc))

    trend = repo.stats("day", now=NOW)["trend"]

    assert trend == [{"bucket": "2026-09-27", "total": 1, "scams": 1}]


def test_stats_window_excludes_old_reports(repo, analyzer):
    save(repo, analyzer, PHISHING, at=NOW - timedelta(days=45))

    assert repo.stats("day", now=NOW)["totals"]["total"] == 0
    assert repo.stats("month", now=NOW)["totals"]["total"] == 1


@pytest.mark.parametrize("period", ["week", "month"])
def test_other_periods_bucket_labels(repo, analyzer, period):
    save(repo, analyzer, PHISHING)

    bucket = repo.stats(period, now=NOW)["trend"][0]["bucket"]

    assert bucket.startswith("2026-")


def test_invalid_period_is_rejected(repo):
    with pytest.raises(ValueError):
        repo.stats("year")


def test_get_returns_stored_details(repo, analyzer):
    code = save(repo, analyzer, PHISHING)

    record = repo.get(code)

    assert record["category"] == "PHISHING"
    assert record["entities"]["urls"] == ["parcel-th-update.cc"]
    assert record["red_flags"]
    assert record["summary"]
    assert repo.get("SA-1999-0001") is None


def test_old_database_is_migrated(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE reports (id INTEGER PRIMARY KEY, report_code TEXT, text_hash TEXT,"
                     " category TEXT, risk INTEGER, impersonated_org TEXT, entities_json TEXT,"
                     " engine TEXT, source TEXT, created_at TEXT)")

    ReportRepository(str(path))

    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reports)")}
    assert {"summary", "red_flags_json"} <= columns


def test_count_and_clear(repo, analyzer):
    save(repo, analyzer, SAFE)
    assert repo.count() == 1

    repo.clear()

    assert repo.count() == 0
