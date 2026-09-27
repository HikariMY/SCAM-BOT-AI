"""LINE Flex Message cards: big, colored, plain-language results for elderly users."""

from dataclasses import dataclass

from app.advice import HOTLINE
from app.models import AnalysisResult
from app.plain_language import TIER_SAFE, plain_verdict

CALL_BUTTON_LABEL = f"📞 โทร {HOTLINE} ปรึกษาฟรี"
DETAILS_BUTTON_LABEL = "ดูรายละเอียด"
DETAILS_POSTBACK_PREFIX = "details="
CALL_BUTTON_COLOR = "#C62828"
TEXT_COLOR = "#1A1A1A"
MUTED_COLOR = "#555555"
EXTRACTED_PREVIEW_CHARS = 80
MAX_ALT_TEXT = 400


@dataclass(frozen=True)
class FlexReply:
    alt_text: str
    contents: dict


def _text(text: str, size: str, **extra) -> dict:
    return {"type": "text", "text": text, "size": size, "wrap": True, **extra}


def _preview(text: str) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= EXTRACTED_PREVIEW_CHARS:
        return one_line
    return one_line[:EXTRACTED_PREVIEW_CHARS] + "…"


def verdict_bubble(result: AnalysisResult) -> dict:
    verdict = plain_verdict(result)
    dont_color = TEXT_COLOR if verdict.tier == TIER_SAFE else CALL_BUTTON_COLOR

    body = [_text(verdict.explanation, "xl", weight="bold", color=TEXT_COLOR),
            {"type": "separator", "margin": "lg"}]
    body += [_text(f"❌ {dont}", "xl", color=dont_color, margin="md") for dont in verdict.donts]
    if result.extracted_text:
        body.append(_text(f"ข้อความในรูป: {_preview(result.extracted_text)}", "sm",
                          color=MUTED_COLOR, margin="lg"))
    body.append(_text(verdict.tip, "md", color=MUTED_COLOR, margin="lg"))

    buttons = [{
        "type": "button", "style": "primary", "color": CALL_BUTTON_COLOR, "height": "md",
        "action": {"type": "uri", "label": CALL_BUTTON_LABEL, "uri": f"tel:{HOTLINE}"},
    }]
    if result.report_code:
        buttons.append({
            "type": "button", "style": "secondary", "height": "md",
            "action": {"type": "postback", "label": DETAILS_BUTTON_LABEL,
                       "data": f"{DETAILS_POSTBACK_PREFIX}{result.report_code}",
                       "displayText": DETAILS_BUTTON_LABEL},
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "20px",
            "backgroundColor": verdict.background,
            "contents": [
                _text(verdict.headline, "xxl", weight="bold", color=verdict.text_color),
                _text(f"ความเสี่ยง {result.risk}%", "lg", color=verdict.text_color, margin="sm"),
            ],
        },
        "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": body},
        "footer": {"type": "box", "layout": "vertical", "spacing": "md", "contents": buttons},
    }


def verdict_reply(result: AnalysisResult) -> FlexReply:
    verdict = plain_verdict(result)
    alt_text = f"{verdict.headline} - {verdict.explanation}"[:MAX_ALT_TEXT]
    return FlexReply(alt_text=alt_text, contents=verdict_bubble(result))
