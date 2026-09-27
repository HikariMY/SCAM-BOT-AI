"""Golden-set tests for the rule engine (the offline fallback)."""

import pytest

from app.models import HIGH_RISK_THRESHOLD, ScamCategory
from app.nlp.domains import inspect_urls
from app.nlp.entities import extract_entities
from app.nlp.rules import SAFE_BELOW, classify_with_rules


def classify(text: str):
    entities = extract_entities(text)
    return classify_with_rules(text, entities, inspect_urls(entities.urls))


SCAM_CASES = [
    ("พัสดุของท่านจัดส่งไม่ได้ เนื่องจากที่อยู่ไม่ครบ กรุณาอัปเดตภายใน 24 ชม. ที่ parcel-th-update.cc",
     ScamCategory.PHISHING),
    ("Kerry: พัสดุตกค้าง กรุณาชำระค่าธรรมเนียม 35 บาท ที่ kerry-th.top ด่วน", ScamCategory.PHISHING),
    ("SCB แจ้งเตือน บัญชีของท่านถูกระงับ กรุณายืนยันตัวตนที่ https://scb-secure.xyz/login",
     ScamCategory.PHISHING),
    ("กรมสรรพากรคืนเงินภาษี 4,500 บาท กรอกข้อมูลบัตรเพื่อรับเงินคืนที่ bit.ly/rd-refund",
     ScamCategory.PHISHING),
    ("เจ้าหน้าที่ตำรวจแจ้งว่าบัญชีของท่านเกี่ยวข้องกับการฟอกเงิน ต้องโอนเงินเพื่อตรวจสอบ "
     "บัญชี 123-4-56789-0 มิฉะนั้นจะออกหมายจับ", ScamCategory.IMPERSONATION),
    ("DSI แจ้งว่าท่านมีหมายเรียกคดียาเสพติด ห้ามบอกใคร ให้แจ้ง OTP เพื่อยืนยันตัวตนทันที",
     ScamCategory.IMPERSONATION),
    ("ลงทุนคริปโต ผลตอบแทน 30% ต่อวัน การันตีไม่มีขาดทุน แอดไลน์ @richfast", ScamCategory.INVESTMENT),
    ("รับสมัครงานออนไลน์ ทำงานที่บ้าน รายได้วันละ 1,500 บาท แอดไลน์เลย", ScamCategory.INVESTMENT),
    ("แม่ ๆ หนูโทรศัพท์หาย ยืมเงินหน่อย ด่วนมาก โอนเงินเข้าบัญชีเพื่อนหนู 1234567890 ก่อนนะ",
     ScamCategory.MONEY_TRANSFER),
    ("ยินดีด้วย คุณถูกรางวัล iPhone ชำระค่าดำเนินการ 500 บาท เพื่อรับรางวัลภายในวันนี้",
     ScamCategory.MONEY_TRANSFER),
]

SAFE_CASES = [
    "สวัสดีครับ พรุ่งนี้ประชุม 10 โมงนะ",
    "พัสดุของคุณจัดส่งเรียบร้อยแล้ว ขอบคุณที่ใช้บริการ",
    "เย็นนี้กินข้าวที่ไหนดี",
    "ดูรายละเอียดโปรโมชันได้ที่ https://www.kasikornbank.com",
    "รหัสสินค้า 9876543210 มาถึงแล้วนะ",
]


@pytest.mark.parametrize(("text", "expected"), SCAM_CASES)
def test_scam_messages_are_classified(text, expected):
    verdict = classify(text)

    assert verdict.category is expected
    assert verdict.risk >= SAFE_BELOW
    assert verdict.red_flags


@pytest.mark.parametrize("text", SAFE_CASES)
def test_safe_messages_score_low(text):
    verdict = classify(text)

    assert verdict.category is ScamCategory.SAFE
    assert verdict.risk < SAFE_BELOW
    assert verdict.impersonated_org is None


def test_slide_example_is_high_risk_logistics_phishing():
    verdict = classify(SCAM_CASES[0][0])

    assert verdict.risk >= HIGH_RISK_THRESHOLD
    assert verdict.impersonated_org == "ขนส่ง"
    assert "เร่งให้รีบทำ" in verdict.red_flags


def test_rule_risk_never_reaches_100():
    text = " ".join(t for t, _ in SCAM_CASES)
    assert classify(text).risk <= 95
