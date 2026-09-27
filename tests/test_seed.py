import random

from app.repository import ReportRepository
from app.demo_seed import RECENT_BURST_COUNT, RECENT_BURST_DOMAIN, seed


def test_seed_creates_reports_with_trend_and_emerging_domain(tmp_path):
    repo = ReportRepository(str(tmp_path / "seed.db"))

    seed(repo, count=60, days=30, rng=random.Random(1))

    stats = repo.stats("day")
    assert repo.count() == 60 + RECENT_BURST_COUNT
    assert stats["totals"]["scams"] > stats["totals"]["total"] // 2
    assert len(stats["by_category"]) >= 4
    assert stats["emerging_domains"][0]["domain"] == RECENT_BURST_DOMAIN
