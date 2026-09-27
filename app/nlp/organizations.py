"""Organizations that scammers commonly impersonate in Thailand.

`official_domains` lets us tell a real link from a lookalike. Aliases in ASCII
are matched on word boundaries; Thai aliases are matched as substrings because
Thai text has no spaces between words.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Organization:
    name: str
    sector: str
    aliases: tuple[str, ...]
    official_domains: tuple[str, ...]


SECTOR_LOGISTICS = "ขนส่ง"
SECTOR_BANK = "ธนาคาร"
SECTOR_GOVERNMENT = "หน่วยงานรัฐ"
SECTOR_TELECOM = "ค่ายมือถือ"
SECTOR_ECOMMERCE = "ร้านค้าออนไลน์"
SECTOR_UTILITY = "สาธารณูปโภค"

ORGANIZATIONS: tuple[Organization, ...] = (
    Organization("Kerry Express", SECTOR_LOGISTICS, ("kerry", "เคอรี่"), ("kerryexpress.com",)),
    Organization("Flash Express", SECTOR_LOGISTICS, ("flash express", "แฟลช"), ("flashexpress.co.th", "flashexpress.com")),
    Organization("ไปรษณีย์ไทย", SECTOR_LOGISTICS, ("ไปรษณีย์", "thailand post", "thailandpost", "thaipost"), ("thailandpost.co.th",)),
    Organization("J&T Express", SECTOR_LOGISTICS, ("j&t", "เจแอนด์ที"), ("jtexpress.co.th",)),
    Organization("ธนาคารกสิกรไทย", SECTOR_BANK, ("กสิกร", "kbank", "kasikorn"), ("kasikornbank.com",)),
    Organization("ธนาคารไทยพาณิชย์", SECTOR_BANK, ("ไทยพาณิชย์", "scb"), ("scb.co.th",)),
    Organization("ธนาคารกรุงเทพ", SECTOR_BANK, ("ธนาคารกรุงเทพ", "bangkok bank", "bualuang"), ("bangkokbank.com",)),
    Organization("ธนาคารกรุงไทย", SECTOR_BANK, ("กรุงไทย", "krungthai", "ktb"), ("krungthai.com",)),
    Organization("ธนาคารกรุงศรีอยุธยา", SECTOR_BANK, ("กรุงศรี", "krungsri"), ("krungsri.com",)),
    Organization("ธนาคารออมสิน", SECTOR_BANK, ("ออมสิน", "gsb"), ("gsb.or.th",)),
    Organization("กรมสรรพากร", SECTOR_GOVERNMENT, ("สรรพากร", "revenue department"), ("rd.go.th",)),
    Organization("สำนักงานตำรวจแห่งชาติ", SECTOR_GOVERNMENT, ("ตำรวจ", "police"), ("police.go.th", "royalthaipolice.go.th")),
    Organization("กรมสอบสวนคดีพิเศษ (DSI)", SECTOR_GOVERNMENT, ("กรมสอบสวนคดีพิเศษ", "dsi"), ("dsi.go.th",)),
    Organization("สำนักงานประกันสังคม", SECTOR_GOVERNMENT, ("ประกันสังคม",), ("sso.go.th",)),
    Organization("การไฟฟ้า", SECTOR_UTILITY, ("การไฟฟ้า", "กฟภ", "กฟน", "pea", "mea"), ("pea.co.th", "mea.or.th")),
    Organization("AIS", SECTOR_TELECOM, ("ais",), ("ais.th", "ais.co.th")),
    Organization("True", SECTOR_TELECOM, ("truemove", "ทรูมูฟ"), ("true.th", "truecorp.co.th")),
    Organization("Shopee", SECTOR_ECOMMERCE, ("shopee", "ช้อปปี้"), ("shopee.co.th",)),
    Organization("Lazada", SECTOR_ECOMMERCE, ("lazada", "ลาซาด้า"), ("lazada.co.th",)),
)

# Generic words that reveal which sector is being impersonated even when no
# specific organization is named, e.g. "พัสดุของท่านจัดส่งไม่ได้".
SECTOR_HINTS: dict[str, tuple[str, ...]] = {
    SECTOR_LOGISTICS: ("พัสดุ", "ขนส่ง", "จัดส่ง", "parcel", "delivery"),
    SECTOR_BANK: ("ธนาคาร", "บัญชีของท่าน", "บัญชีถูก", "บัตรเครดิต"),
    SECTOR_GOVERNMENT: ("หมายเรียก", "หมายจับ", "ศาล", "ดำเนินคดี", "ภาษี"),
    SECTOR_UTILITY: ("ค่าไฟ", "ค่าน้ำ", "มิเตอร์"),
}


def _alias_pattern(alias: str) -> re.Pattern[str]:
    if alias.isascii():
        return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", re.IGNORECASE)
    return re.compile(re.escape(alias))


_ALIAS_PATTERNS: tuple[tuple[Organization, tuple[re.Pattern[str], ...]], ...] = tuple(
    (org, tuple(_alias_pattern(a) for a in org.aliases)) for org in ORGANIZATIONS
)


def find_organizations(text: str) -> tuple[Organization, ...]:
    return tuple(
        org for org, patterns in _ALIAS_PATTERNS if any(p.search(text) for p in patterns)
    )


def detect_sector(text: str) -> str | None:
    lowered = text.lower()
    for sector, hints in SECTOR_HINTS.items():
        if any(hint in lowered for hint in hints):
            return sector
    return None


def is_official_host(host: str) -> bool:
    host = host.lower()
    return any(
        host == domain or host.endswith("." + domain)
        for org in ORGANIZATIONS
        for domain in org.official_domains
    )


def brand_keywords() -> tuple[str, ...]:
    """ASCII brand names (3+ chars) used to spot lookalike domains."""
    return tuple(
        alias.replace(" ", "")
        for org in ORGANIZATIONS
        for alias in org.aliases
        if alias.isascii() and len(alias) >= 3 and "&" not in alias
    )
