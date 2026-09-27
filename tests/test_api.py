import base64

import pytest
from fastapi.testclient import TestClient

from app.analyzer import ScamAnalyzer
from app.config import Settings
from app.main import ANALYZE_RATE_LIMIT, create_app, seed_if_empty
from app.models import ScamCategory, Verdict
from app.rate_limit import RateLimiter
from app.repository import ReportRepository

SLIDE_TEXT = "พัสดุของท่านจัดส่งไม่ได้ เนื่องจากที่อยู่ไม่ครบ กรุณาอัปเดตภายใน 24 ชม. ที่ parcel-th-update.cc"


def make_settings(tmp_path) -> Settings:
    return Settings(gemini_api_key=None, gemini_model="test", line_channel_secret=None,
                    line_channel_access_token=None, database_path=str(tmp_path / "api.db"))


@pytest.fixture
def client(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings, ScamAnalyzer(), ReportRepository(settings.database_path))
    return TestClient(app)


def test_health_reports_engine_and_line_status(client):
    body = client.get("/health").json()

    assert body == {"success": True, "data": {"engine": "rules", "line": False}, "error": None}


def test_analyze_returns_report(client):
    body = client.post("/api/analyze", json={"text": SLIDE_TEXT}).json()

    assert body["success"] is True
    assert body["data"]["category"] == "PHISHING"
    assert body["data"]["report_code"] == "SA-" + body["data"]["report_code"][3:]


def test_analyze_rejects_blank_text(client):
    response = client.post("/api/analyze", json={"text": "   "})

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_analyze_rejects_missing_field(client):
    assert client.post("/api/analyze", json={}).status_code == 422


def test_analyze_is_rate_limited(client):
    for _ in range(ANALYZE_RATE_LIMIT):
        client.post("/api/analyze", json={"text": "hello world test"})

    response = client.post("/api/analyze", json={"text": "hello world test"})

    assert response.status_code == 429


def test_stats_endpoint(client):
    client.post("/api/analyze", json={"text": SLIDE_TEXT})

    body = client.get("/api/stats?period=week").json()

    assert body["data"]["period"] == "week"
    assert body["data"]["totals"]["scams"] == 1


def test_stats_rejects_unknown_period(client):
    assert client.get("/api/stats?period=year").status_code == 422


def test_callback_without_line_config_is_503(client):
    assert client.post("/callback", content="{}").status_code == 503


def test_callback_with_bad_signature_is_400(tmp_path):
    settings = make_settings(tmp_path)
    settings = Settings(**{**settings.__dict__, "line_channel_secret": "s", "line_channel_access_token": "t"})
    client = TestClient(create_app(settings, ScamAnalyzer(), ReportRepository(settings.database_path)))

    response = client.post("/callback", content='{"events":[]}', headers={"X-Line-Signature": "bad"})

    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/try", "/dashboard"])
def test_pages_are_served(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_root_serves_check_page_directly(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_pwa_files_are_served_from_root(client):
    manifest = client.get("/manifest.webmanifest")
    worker = client.get("/sw.js")

    assert manifest.json()["start_url"] == "/"
    assert "javascript" in worker.headers["content-type"]


def test_analyze_payload_includes_plain_verdict(client):
    data = client.post("/api/analyze", json={"text": SLIDE_TEXT}).json()["data"]

    assert data["verdict"]["tier"] == "danger"
    assert data["verdict"]["donts"]


PNG_B64 = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 16).decode()


class VisionLLM:
    name = "fake"

    def classify(self, text, entities, findings):
        return Verdict(ScamCategory.PHISHING, 88, (), "หลอก", None)

    def extract_text(self, image, mime_type):
        return SLIDE_TEXT


def test_analyze_image_without_ai_is_422(client):
    body = client.post("/api/analyze-image", json={"image": PNG_B64}).json()

    assert body["success"] is False
    assert "คัดลอกข้อความ" in body["error"]


def test_analyze_image_rejects_invalid_base64(client):
    assert client.post("/api/analyze-image", json={"image": "data:image/png;base64,@@@"}).status_code == 422


def test_analyze_image_with_ai(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings, ScamAnalyzer(VisionLLM()), ReportRepository(settings.database_path))

    data = TestClient(app).post("/api/analyze-image", json={"image": PNG_B64}).json()["data"]

    assert data["extracted_text"] == SLIDE_TEXT
    assert data["risk"] == 88
    assert data["report_code"].startswith("SA-")


def test_seed_if_empty_only_seeds_once(tmp_path):
    repo = ReportRepository(str(tmp_path / "seed.db"))

    seed_if_empty(repo)
    first = repo.count()
    seed_if_empty(repo)

    assert first > 0
    assert repo.count() == first


def test_rate_limiter_window_expires():
    now = [0.0]
    limiter = RateLimiter(1, 10, clock=lambda: now[0])

    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    now[0] = 10.0
    assert limiter.allow("a") is True
