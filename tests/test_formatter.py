from dataclasses import replace

from linebot.v3.messaging import FlexContainer

from app import formatter
from app.analyzer import ScamAnalyzer
from app.line_flex import CALL_BUTTON_LABEL, DETAILS_POSTBACK_PREFIX, verdict_bubble, verdict_reply
from app.models import ScamCategory
from app.plain_language import TIER_DANGER, TIER_SAFE, TIER_WARNING, plain_verdict, result_payload, tier_for

SLIDE_TEXT = "พัสดุของท่านจัดส่งไม่ได้ เนื่องจากที่อยู่ไม่ครบ กรุณาอัปเดตภายใน 24 ชม. ที่ parcel-th-update.cc"
SAFE_TEXT = "พรุ่งนี้ประชุม 10 โมงนะ"


def analyze(text):
    return ScamAnalyzer().analyze(text)


def test_defang_makes_links_unclickable():
    assert formatter.defang("https://parcel-th-update.cc/a") == "hxxps://parcel-th-update[.]cc/a"


class TestPlainVerdict:
    def test_tiers_follow_risk_and_category(self):
        assert tier_for(ScamCategory.PHISHING, 90) == TIER_DANGER
        assert tier_for(ScamCategory.PHISHING, 20) == TIER_WARNING
        assert tier_for(ScamCategory.SAFE, 50) == TIER_WARNING
        assert tier_for(ScamCategory.SAFE, 5) == TIER_SAFE

    def test_scam_uses_plain_words_not_jargon(self):
        verdict = plain_verdict(analyze(SLIDE_TEXT))

        assert verdict.headline.startswith("🔴 อันตราย")
        assert "PHISHING" not in verdict.explanation
        assert "อย่ากดลิงก์" in verdict.donts

    def test_impersonation_names_the_organization(self):
        result = replace(analyze(SLIDE_TEXT), category=ScamCategory.IMPERSONATION, impersonated_org="ตำรวจ")

        assert "แอบอ้างเป็นตำรวจ" in plain_verdict(result).explanation

    def test_safe_category_with_medium_risk_is_not_called_safe(self):
        result = replace(analyze(SAFE_TEXT), risk=50)

        verdict = plain_verdict(result)

        assert verdict.tier == TIER_WARNING
        assert "ยังไม่พบสิ่งผิดปกติ" not in verdict.explanation

    def test_payload_includes_verdict(self):
        payload = result_payload(analyze(SAFE_TEXT))

        assert payload["verdict"]["tier"] == TIER_SAFE
        assert payload["category"] == "SAFE"


class TestFlexCard:
    def test_card_is_valid_line_flex(self):
        bubble = verdict_bubble(replace(analyze(SLIDE_TEXT), report_code="SA-2026-0001"))

        FlexContainer.from_dict(bubble)  # raises if the structure is invalid

    def test_card_has_call_and_details_buttons(self):
        bubble = verdict_bubble(replace(analyze(SLIDE_TEXT), report_code="SA-2026-0001"))

        actions = [b["action"] for b in bubble["footer"]["contents"]]
        assert actions[0] == {"type": "uri", "label": CALL_BUTTON_LABEL, "uri": "tel:1441"}
        assert actions[1]["data"] == f"{DETAILS_POSTBACK_PREFIX}SA-2026-0001"

    def test_card_without_report_code_has_only_call_button(self):
        assert len(verdict_bubble(analyze(SAFE_TEXT))["footer"]["contents"]) == 1

    def test_card_shows_preview_of_text_read_from_image(self):
        result = replace(analyze(SLIDE_TEXT), extracted_text="ก" * 200)

        texts = [c["text"] for c in verdict_bubble(result)["body"]["contents"] if c["type"] == "text"]

        assert any(t.startswith("ข้อความในรูป:") and t.endswith("…") for t in texts)

    def test_alt_text_is_plain_summary(self):
        assert verdict_reply(analyze(SLIDE_TEXT)).alt_text.startswith("🔴 อันตราย")


def test_format_details_from_stored_record():
    record = {
        "report_code": "SA-2026-0001", "category": "PHISHING", "risk": 92,
        "impersonated_org": "ขนส่ง", "summary": "หลอกกดลิงก์",
        "red_flags": ["เร่งเวลา"], "entities": {"urls": ["parcel-th-update.cc"], "phones": []},
    }

    text = formatter.format_details(record)

    assert "รายละเอียดรายงาน SA-2026-0001" in text
    assert "Text Classification" in text and "Named Entity Recognition" in text
    assert "Text Summarization" in text
    assert "ประเภท: ลิงก์ปลอม (PHISHING)" in text
    assert "แอบอ้างเป็น: ขนส่ง" in text
    assert "parcel-th-update[.]cc" in text
    assert "เบอร์โทร" not in text


def test_format_details_without_entities_says_none_found():
    record = {
        "report_code": "SA-2026-0002", "category": "SAFE", "risk": 5,
        "impersonated_org": None, "summary": "", "red_flags": [], "entities": {},
    }

    assert "ไม่พบลิงก์ เบอร์โทร หรือเลขบัญชี" in formatter.format_details(record)


def test_format_stats_lists_top_items():
    stats = {
        "totals": {"total": 10, "scams": 7, "high_risk": 5},
        "by_category": [{"category": "PHISHING", "label": "ลิงก์ปลอม", "count": 5},
                        {"category": "SAFE", "label": "ปลอดภัย", "count": 3}],
        "by_org": [{"org": "ขนส่ง", "count": 4}],
        "emerging_domains": [{"domain": "bad.cc", "count": 3}],
    }

    text = formatter.format_stats(stats)

    assert "ตรวจทั้งหมด 10 ข้อความ พบกลโกง 7 ข้อความ" in text
    assert "ลิงก์ปลอม: 5" in text
    assert "ปลอดภัย" not in text
    assert "bad[.]cc (3 ครั้ง)" in text
