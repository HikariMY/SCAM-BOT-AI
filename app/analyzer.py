"""Pipeline: entity extraction, URL inspection, classification, advice."""

import logging
from dataclasses import replace

from app.advice import advice_for
from app.models import AnalysisResult, ScamCategory, Verdict
from app.nlp.domains import inspect_urls
from app.nlp.entities import extract_entities
from app.nlp.llm import LLMError, LLMProvider, NoTextFoundError
from app.nlp.rules import classify_with_rules

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 2000
MAX_IMAGE_BYTES = 5 * 1024 * 1024

MSG_IMAGE_NEEDS_AI = "ตอนนี้ระบบยังตรวจรูปไม่ได้ กรุณาคัดลอกข้อความมาวางแทน"
MSG_IMAGE_TOO_LARGE = "รูปใหญ่เกินไป ลองแคปหน้าจอใหม่แล้วส่งอีกครั้ง"
MSG_IMAGE_UNSUPPORTED = "ไฟล์นี้ไม่ใช่รูปที่รองรับ กรุณาส่งรูปแคปหน้าจอ (JPG หรือ PNG)"
MSG_IMAGE_NO_TEXT = "ไม่พบข้อความในรูป ลองแคปหน้าจอให้เห็นข้อความชัดๆ แล้วส่งใหม่"
MSG_IMAGE_FAILED = "อ่านรูปไม่สำเร็จชั่วคราว ลองส่งใหม่อีกครั้ง หรือคัดลอกข้อความมาวางแทน"
# A confirmed fake domain is hard evidence; the LLM may not score below this.
FAKE_DOMAIN_RISK_FLOOR = 70
MAX_RED_FLAGS = 5


class ScamAnalyzer:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm

    @property
    def engine_name(self) -> str:
        return self._llm.name if self._llm else "rules"

    def analyze(self, text: str) -> AnalysisResult:
        text = normalize_input(text)
        entities = extract_entities(text)
        findings = inspect_urls(entities.urls)
        rule_verdict = classify_with_rules(text, entities, findings)

        verdict, engine = rule_verdict, "rules"
        if self._llm is not None:
            try:
                llm_verdict = self._llm.classify(text, entities, findings)
                verdict, engine = merge_verdicts(llm_verdict, rule_verdict, findings), self._llm.name
            except LLMError as exc:
                logger.warning("LLM unavailable, using rule engine: %s", exc)

        return AnalysisResult(
            category=verdict.category,
            risk=verdict.risk,
            red_flags=verdict.red_flags,
            summary=verdict.summary,
            advice=advice_for(verdict.category),
            entities=entities,
            domain_findings=findings,
            impersonated_org=verdict.impersonated_org,
            engine=engine,
        )

    def analyze_image(self, image: bytes) -> AnalysisResult:
        if self._llm is None:
            raise ImageAnalysisError(MSG_IMAGE_NEEDS_AI)
        if len(image) > MAX_IMAGE_BYTES:
            raise ImageAnalysisError(MSG_IMAGE_TOO_LARGE)
        mime_type = detect_image_type(image)
        if mime_type is None:
            raise ImageAnalysisError(MSG_IMAGE_UNSUPPORTED)
        try:
            text = self._llm.extract_text(image, mime_type)
        except NoTextFoundError as exc:
            raise ImageAnalysisError(MSG_IMAGE_NO_TEXT) from exc
        except LLMError as exc:
            logger.warning("Image text extraction failed: %s", exc)
            raise ImageAnalysisError(MSG_IMAGE_FAILED) from exc
        result = self.analyze(text)
        return replace(result, extracted_text=normalize_input(text))


class ImageAnalysisError(Exception):
    """Image could not be analyzed; the message is safe to show to users (Thai)."""


def detect_image_type(data: bytes) -> str | None:
    """Identify the image format from magic bytes instead of trusting the client."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_input(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text is empty")
    return cleaned[:MAX_TEXT_LENGTH]


def merge_verdicts(llm: Verdict, rules: Verdict, findings) -> Verdict:
    has_fake_domain = any(f.is_suspicious for f in findings)
    risk = max(llm.risk, FAKE_DOMAIN_RISK_FLOOR) if has_fake_domain else llm.risk
    category = llm.category
    if category is ScamCategory.SAFE and has_fake_domain:
        category = ScamCategory.PHISHING
    red_flags = tuple(dict.fromkeys(llm.red_flags + rules.red_flags))[:MAX_RED_FLAGS]
    org = llm.impersonated_org or rules.impersonated_org
    if category is ScamCategory.SAFE:
        org = None
    summary = llm.summary or rules.summary
    return Verdict(category, risk, red_flags, summary, org)
