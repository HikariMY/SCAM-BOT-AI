"""Rule-based scam classifier.

Runs without any external service. The analyzer uses it as the fallback when
the LLM is unavailable and as a floor for risk when hard evidence (fake
domains) exists.
"""

import re
from dataclasses import dataclass

from app.models import DomainFinding, Entities, ScamCategory, Verdict
from app.nlp import domains
from app.nlp.organizations import detect_sector, find_organizations


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    weight: int
    pattern: re.Pattern[str]


def _signal(key: str, label: str, weight: int, pattern: str) -> Signal:
    return Signal(key, label, weight, re.compile(pattern, re.IGNORECASE))


SIGNALS: tuple[Signal, ...] = (
    _signal("urgency", "เร่งให้รีบทำ", 15,
            r"ภายใน\s*\d+\s*(?:ชม|ชั่วโมง|นาที|วัน)|ด่วน|ทันที|ภายในวันนี้|หมดเขต|ครั้งสุดท้าย|โดยเร็ว"),
    _signal("threat", "ขู่ให้กลัว", 25,
            r"ระงับ|อายัด|ดำเนินคดี|หมายจับ|หมายเรียก|ผิดกฎหมาย|ฟอกเงิน|ถูกปิด|ค่าปรับ|ยาเสพติด|ถูกตัด"),
    _signal("credentials", "ขอข้อมูลส่วนตัว/OTP", 25,
            r"otp|รหัสผ่าน|password|เลขบัตรประชาชน|ยืนยันตัวตน|กรอกข้อมูล|เลขหลังบัตร|cvv|ข้อมูลบัตร|อัปเดตข้อมูล|อัพเดทข้อมูล"),
    _signal("payment", "ขอให้โอนหรือชำระเงิน", 20,
            r"โอนเงิน|โอนมา|โอนเข้า|โอนค่า|ชำระ|ค่าธรรมเนียม|ค่ามัดจำ|วางเงิน|ค่าดำเนินการ"),
    _signal("investment", "อ้างผลตอบแทนสูงเกินจริง", 25,
            r"ผลตอบแทน|ปันผล|กำไร\s*\d|การันตี|คริปโต|crypto|เทรด|ลงทุน|รายได้เสริม|รายได้ต่อวัน|งานออนไลน์|ทำงานที่บ้าน|forex"),
    _signal("unrealistic_return", "ผลตอบแทนต่อวัน/สัปดาห์สูงผิดปกติ", 20,
            r"\d+\s*%\s*(?:ต่อ|/)\s*(?:วัน|สัปดาห์|อาทิตย์|เดือน)|วันละ\s*\d[\d,]*\s*บาท"),
    _signal("prize", "อ้างรางวัลหรือเงินคืน", 15,
            r"ได้รับรางวัล|ถูกรางวัล|โชคดี|คืนเงิน|เงินคืน|refund|สิทธิ์พิเศษ|รับฟรี"),
    _signal("off_platform", "ชวนแอด LINE/ติดต่อช่องทางอื่น", 10,
            r"แอดไลน์|แอด\s*line|add\s*line|line\s*id|ไอดีไลน์"),
    _signal("click_link", "ให้กดลิงก์", 10,
            r"กดลิงก์|คลิกลิงก์|คลิก|กดที่ลิงก์|ที่ลิงก์|อัปเดต.{0,20}ที่|อัพเดท.{0,20}ที่"),
)

DOMAIN_FLAG_WEIGHTS = {
    domains.FLAG_FAKE_DOMAIN: 30,
    domains.FLAG_IP_HOST: 25,
    domains.FLAG_SHORTENER: 20,
    domains.FLAG_RISKY_TLD: 15,
    domains.FLAG_LURE_WORDS: 10,
    domains.FLAG_NOT_HTTPS: 5,
}

BASE_RISK = 5
UNKNOWN_LINK_RISK = 5
ACCOUNT_NUMBER_RISK = 10
NAMED_ORG_RISK = 10
MULTI_SIGNAL_BONUS = 10
MULTI_SIGNAL_COUNT = 3
MAX_RULE_RISK = 95
SAFE_BELOW = 30
MAX_RED_FLAGS = 5

SUMMARIES = {
    ScamCategory.PHISHING: "หลอกให้กดลิงก์ปลอมเพื่อขโมยข้อมูลส่วนตัวหรือข้อมูลบัตร",
    ScamCategory.MONEY_TRANSFER: "หลอกให้โอนเงินเข้าบัญชีของมิจฉาชีพ",
    ScamCategory.IMPERSONATION: "แอบอ้างเป็น{org}เพื่อข่มขู่หรือหลอกเอาเงินและข้อมูล",
    ScamCategory.INVESTMENT: "ชวนลงทุนหรือหารายได้โดยอ้างผลตอบแทนสูงเกินจริง",
    ScamCategory.SAFE: "ไม่พบลักษณะของมิจฉาชีพที่ชัดเจน",
}


def _matched_signals(text: str) -> tuple[Signal, ...]:
    return tuple(s for s in SIGNALS if s.pattern.search(text))


def _domain_score(findings: tuple[DomainFinding, ...]) -> int:
    score = 0
    for finding in findings:
        score += UNKNOWN_LINK_RISK if finding.host else 0
        score += sum(DOMAIN_FLAG_WEIGHTS.get(flag, 0) for flag in finding.flags)
    return score


def _domain_labels(findings: tuple[DomainFinding, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(flag for f in findings for flag in f.flags))


def _impersonated(text: str) -> str | None:
    orgs = find_organizations(text)
    return orgs[0].name if orgs else detect_sector(text)


def _pick_category(keys: set[str], entities: Entities,
                   findings: tuple[DomainFinding, ...], impersonated: str | None) -> ScamCategory:
    if keys & {"investment", "unrealistic_return"}:
        return ScamCategory.INVESTMENT
    bad_link = any(f.is_suspicious for f in findings)
    if bad_link or (entities.urls and keys & {"credentials", "click_link"}):
        return ScamCategory.PHISHING
    if impersonated and keys & {"threat", "credentials"}:
        return ScamCategory.IMPERSONATION
    if "payment" in keys or entities.accounts:
        return ScamCategory.MONEY_TRANSFER
    if entities.urls:
        return ScamCategory.PHISHING
    return ScamCategory.IMPERSONATION if impersonated else ScamCategory.MONEY_TRANSFER


def classify_with_rules(text: str, entities: Entities,
                        findings: tuple[DomainFinding, ...]) -> Verdict:
    signals = _matched_signals(text)
    domain_labels = _domain_labels(findings)

    risk = BASE_RISK + sum(s.weight for s in signals) + _domain_score(findings)
    if signals and entities.accounts:
        risk += ACCOUNT_NUMBER_RISK
    if signals and entities.organizations:
        risk += NAMED_ORG_RISK
    if len(signals) + len(domain_labels) >= MULTI_SIGNAL_COUNT:
        risk += MULTI_SIGNAL_BONUS
    risk = min(risk, MAX_RULE_RISK)

    red_flags = (tuple(s.label for s in signals) + domain_labels)[:MAX_RED_FLAGS]
    if risk < SAFE_BELOW:
        return Verdict(ScamCategory.SAFE, risk, red_flags, SUMMARIES[ScamCategory.SAFE])

    impersonated = _impersonated(text)
    category = _pick_category({s.key for s in signals}, entities, findings, impersonated)
    summary = SUMMARIES[category].format(org=impersonated or "หน่วยงาน")
    return Verdict(category, risk, red_flags, summary, impersonated)
