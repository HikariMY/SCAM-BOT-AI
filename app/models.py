"""Domain types shared across the analyzer, storage and presentation layers."""

from dataclasses import dataclass, field
from enum import Enum


class ScamCategory(str, Enum):
    PHISHING = "PHISHING"
    MONEY_TRANSFER = "MONEY_TRANSFER"
    IMPERSONATION = "IMPERSONATION"
    INVESTMENT = "INVESTMENT"
    SAFE = "SAFE"

    @property
    def thai_label(self) -> str:
        return CATEGORY_THAI_LABELS[self]


CATEGORY_THAI_LABELS = {
    ScamCategory.PHISHING: "ลิงก์ปลอม",
    ScamCategory.MONEY_TRANSFER: "หลอกโอนเงิน",
    ScamCategory.IMPERSONATION: "แอบอ้างหน่วยงาน",
    ScamCategory.INVESTMENT: "หลอกลงทุน",
    ScamCategory.SAFE: "ไม่พบความเสี่ยงชัดเจน",
}


@dataclass(frozen=True)
class Entities:
    phones: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    accounts: tuple[str, ...] = ()
    amounts: tuple[str, ...] = ()
    organizations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "phones": list(self.phones),
            "urls": list(self.urls),
            "accounts": list(self.accounts),
            "amounts": list(self.amounts),
            "organizations": list(self.organizations),
        }


@dataclass(frozen=True)
class DomainFinding:
    host: str
    flags: tuple[str, ...]

    @property
    def is_suspicious(self) -> bool:
        return bool(self.flags)


@dataclass(frozen=True)
class Verdict:
    """Classification output from either the LLM or the rule engine."""

    category: ScamCategory
    risk: int
    red_flags: tuple[str, ...]
    summary: str
    impersonated_org: str | None = None


@dataclass(frozen=True)
class AnalysisResult:
    category: ScamCategory
    risk: int
    red_flags: tuple[str, ...]
    summary: str
    advice: str
    entities: Entities
    domain_findings: tuple[DomainFinding, ...] = ()
    impersonated_org: str | None = None
    engine: str = "rules"
    report_code: str | None = field(default=None)
    # Text read from a screenshot, shown back so users can see what was checked.
    extracted_text: str | None = None

    @property
    def risk_level(self) -> str:
        if self.risk >= HIGH_RISK_THRESHOLD:
            return "สูง"
        if self.risk >= MEDIUM_RISK_THRESHOLD:
            return "ปานกลาง"
        return "ต่ำ"

    def to_dict(self) -> dict:
        return {
            "report_code": self.report_code,
            "category": self.category.value,
            "category_label": self.category.thai_label,
            "risk": self.risk,
            "risk_level": self.risk_level,
            "red_flags": list(self.red_flags),
            "summary": self.summary,
            "advice": self.advice,
            "impersonated_org": self.impersonated_org,
            "entities": self.entities.to_dict(),
            "domains": [
                {"host": f.host, "flags": list(f.flags)} for f in self.domain_findings
            ],
            "engine": self.engine,
            "extracted_text": self.extracted_text,
        }


HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 40
