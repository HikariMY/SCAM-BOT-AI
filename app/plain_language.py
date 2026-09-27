"""Plain-language verdicts for elderly and non-technical users.

Technical labels like "PHISHING" mean nothing to most users, so every result
is also expressed as a traffic light, one short sentence and a few "don'ts".
"""

from dataclasses import dataclass

from app.advice import HOTLINE
from app.models import HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD, AnalysisResult, ScamCategory

TIER_DANGER = "danger"
TIER_WARNING = "warning"
TIER_SAFE = "safe"


@dataclass(frozen=True)
class TierStyle:
    headline: str
    background: str
    text_color: str


TIER_STYLES = {
    TIER_DANGER: TierStyle("🔴 อันตราย! น่าจะเป็นมิจฉาชีพ", "#C62828", "#FFFFFF"),
    TIER_WARNING: TierStyle("🟡 น่าสงสัย ระวังไว้ก่อน", "#F9A825", "#1A1A1A"),
    TIER_SAFE: TierStyle("🟢 ไม่พบอันตรายชัดเจน", "#2E7D32", "#FFFFFF"),
}

EXPLANATIONS = {
    ScamCategory.PHISHING: "ข้อความนี้หลอกให้กดลิงก์ เพื่อขโมยข้อมูลหรือเงินในบัญชี",
    ScamCategory.MONEY_TRANSFER: "ข้อความนี้หลอกให้โอนเงิน",
    ScamCategory.IMPERSONATION: "มีคนแอบอ้างเป็น{org} เพื่อหลอกเอาเงินหรือข้อมูล",
    ScamCategory.INVESTMENT: "ชวนลงทุนหรือหารายได้ที่ดีเกินจริง มักเป็นกลโกง",
    ScamCategory.SAFE: "ยังไม่พบสิ่งผิดปกติ แต่ถ้ามีใครขอเงินหรือขอรหัส ให้ถามคนในครอบครัวก่อน",
}
UNCLEAR_EXPLANATION = "มีบางจุดน่าสงสัย ควรถามคนในครอบครัวก่อนทำตาม"

DONTS = {
    ScamCategory.PHISHING: ("อย่ากดลิงก์", "อย่ากรอกรหัสหรือเลขบัตร"),
    ScamCategory.MONEY_TRANSFER: ("อย่าโอนเงิน", "โทรถามคนที่รู้จักโดยตรงก่อน"),
    ScamCategory.IMPERSONATION: ("อย่าโอนเงิน", "อย่าบอกรหัส OTP กับใคร"),
    ScamCategory.INVESTMENT: ("อย่าโอนเงินลงทุน", "อย่าแอดไลน์คนแปลกหน้า"),
    ScamCategory.SAFE: ("อย่าบอกรหัส OTP กับใคร",),
}

FAMILY_TIP = f"ไม่แน่ใจ ส่งให้ลูกหลานดู หรือโทร {HOTLINE} ปรึกษาฟรี 24 ชม."
DEFAULT_IMPERSONATED = "เจ้าหน้าที่"


@dataclass(frozen=True)
class PlainVerdict:
    tier: str
    headline: str
    explanation: str
    donts: tuple[str, ...]
    background: str
    text_color: str
    tip: str = FAMILY_TIP

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "headline": self.headline,
            "explanation": self.explanation,
            "donts": list(self.donts),
            "background": self.background,
            "text_color": self.text_color,
            "tip": self.tip,
        }


def tier_for(category: ScamCategory, risk: int) -> str:
    if risk >= HIGH_RISK_THRESHOLD:
        return TIER_DANGER
    if risk >= MEDIUM_RISK_THRESHOLD or category is not ScamCategory.SAFE:
        return TIER_WARNING
    return TIER_SAFE


def plain_verdict(result: AnalysisResult) -> PlainVerdict:
    tier = tier_for(result.category, result.risk)
    style = TIER_STYLES[tier]
    if result.category is ScamCategory.SAFE and tier != TIER_SAFE:
        explanation = UNCLEAR_EXPLANATION
    else:
        org = result.impersonated_org or DEFAULT_IMPERSONATED
        explanation = EXPLANATIONS[result.category].format(org=org)
    return PlainVerdict(
        tier=tier,
        headline=style.headline,
        explanation=explanation,
        donts=DONTS[result.category],
        background=style.background,
        text_color=style.text_color,
    )


def result_payload(result: AnalysisResult) -> dict:
    """API payload: technical result plus the plain-language verdict."""
    return result.to_dict() | {"verdict": plain_verdict(result).to_dict()}
