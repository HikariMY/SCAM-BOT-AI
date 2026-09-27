"""FastAPI entry point.

Run with:  uvicorn app.main:create_app --factory --reload
"""

import base64
import binascii
import logging
import random
from dataclasses import replace
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from linebot.v3.exceptions import InvalidSignatureError
from pydantic import BaseModel, Field

from app.analyzer import MAX_IMAGE_BYTES, ImageAnalysisError, ScamAnalyzer
from app.config import Settings, load_settings
from app.demo_seed import DEFAULT_DAYS, seed
from app.line_handler import LineBot
from app.models import AnalysisResult
from app.nlp.llm import GeminiProvider
from app.plain_language import result_payload
from app.rate_limit import RateLimiter
from app.repository import ReportRepository

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"
ANALYZE_RATE_LIMIT = 20
IMAGE_RATE_LIMIT = 6
RATE_WINDOW_SECONDS = 60
MAX_REQUEST_TEXT = 5000
# Base64 inflates data by 4/3; allow some slack for the data-URL prefix.
MAX_IMAGE_BASE64_CHARS = MAX_IMAGE_BYTES * 4 // 3 + 1024
DEMO_SEED_COUNT = 200
MSG_TOO_MANY_REQUESTS = "ส่งถี่เกินไป กรุณารอสักครู่แล้วลองใหม่"
MSG_BAD_IMAGE = "อ่านไฟล์รูปไม่ได้ กรุณาเลือกรูปใหม่อีกครั้ง"


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_REQUEST_TEXT)


class AnalyzeImageRequest(BaseModel):
    image: str = Field(min_length=1, max_length=MAX_IMAGE_BASE64_CHARS,
                       description="Base64 image, optionally as a data URL")


def envelope(data=None, error: str | None = None, status: int = 200) -> JSONResponse:
    return JSONResponse({"success": error is None, "data": data, "error": error}, status_code=status)


def decode_image(value: str) -> bytes:
    _, _, payload = value.rpartition(",")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(MSG_BAD_IMAGE) from exc


def build_analyzer(settings: Settings) -> ScamAnalyzer:
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set; running with the rule engine only")
        return ScamAnalyzer()
    return ScamAnalyzer(GeminiProvider(settings.gemini_api_key, settings.gemini_models))


def seed_if_empty(repository: ReportRepository) -> None:
    # Free hosts wipe the disk on restart; refill so the dashboard never looks empty in a demo.
    if repository.count() == 0:
        seed(repository, DEMO_SEED_COUNT, DEFAULT_DAYS, random.Random())
        logger.info("Seeded %d demo reports", repository.count())


def create_app(settings: Settings | None = None, analyzer: ScamAnalyzer | None = None,
               repository: ReportRepository | None = None, line_bot: LineBot | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or load_settings()
    analyzer = analyzer or build_analyzer(settings)
    repository = repository or ReportRepository(settings.database_path)
    if settings.seed_demo_if_empty:
        seed_if_empty(repository)
    if line_bot is None and settings.line_enabled:
        line_bot = LineBot(settings.line_channel_secret, settings.line_channel_access_token,
                           analyzer, repository)
    text_limiter = RateLimiter(ANALYZE_RATE_LIMIT, RATE_WINDOW_SECONDS)
    image_limiter = RateLimiter(IMAGE_RATE_LIMIT, RATE_WINDOW_SECONDS)

    def saved_payload(result: AnalysisResult, text: str) -> dict:
        code = repository.save(result, text, source="web")
        return result_payload(replace(result, report_code=code))

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    app = FastAPI(title="Scam Alert Bot")
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/try", include_in_schema=False)
    def check_page():
        return FileResponse(WEB_DIR / "try.html")

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_page():
        return FileResponse(WEB_DIR / "dashboard.html")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        # Served from the root so the worker's scope covers the whole site.
        return FileResponse(WEB_DIR / "sw.js", media_type="text/javascript")

    @app.get("/health")
    def health():
        return envelope({"engine": analyzer.engine_name, "line": line_bot is not None})

    @app.post("/api/analyze")
    def analyze(payload: AnalyzeRequest, request: Request):
        if not text_limiter.allow(client_key(request)):
            return envelope(error=MSG_TOO_MANY_REQUESTS, status=429)
        try:
            result = analyzer.analyze(payload.text)
        except ValueError as exc:
            return envelope(error=str(exc), status=422)
        return envelope(saved_payload(result, payload.text))

    @app.post("/api/analyze-image")
    def analyze_image(payload: AnalyzeImageRequest, request: Request):
        if not image_limiter.allow(client_key(request)):
            return envelope(error=MSG_TOO_MANY_REQUESTS, status=429)
        try:
            result = analyzer.analyze_image(decode_image(payload.image))
        except (ValueError, ImageAnalysisError) as exc:
            return envelope(error=str(exc), status=422)
        return envelope(saved_payload(result, result.extracted_text or ""))

    @app.get("/api/stats")
    def stats(period: Literal["day", "week", "month"] = "day"):
        return envelope(repository.stats(period))

    @app.post("/callback")
    async def line_callback(request: Request, x_line_signature: str = Header(default="")):
        if line_bot is None:
            raise HTTPException(status_code=503, detail="LINE channel is not configured")
        body = (await request.body()).decode("utf-8")
        try:
            await run_in_threadpool(line_bot.handle, body, x_line_signature)
        except InvalidSignatureError:
            raise HTTPException(status_code=400, detail="Invalid signature")
        return "OK"

    return app
