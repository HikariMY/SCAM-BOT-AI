"""Static inspection of URLs. Links are never fetched, so there is no SSRF risk."""

import ipaddress
import re
from urllib.parse import urlsplit

from app.models import DomainFinding
from app.nlp.organizations import brand_keywords, is_official_host

FLAG_FAKE_DOMAIN = "โดเมนปลอม/เลียนแบบแบรนด์"
FLAG_RISKY_TLD = "นามสกุลโดเมนที่มิจฉาชีพนิยมใช้"
FLAG_SHORTENER = "ลิงก์ย่อซ่อนปลายทาง"
FLAG_IP_HOST = "ลิงก์เป็นเลข IP"
FLAG_LURE_WORDS = "ชื่อโดเมนมีคำล่อ เช่น update/verify"
FLAG_NOT_HTTPS = "ลิงก์ไม่ใช้ HTTPS"

RISKY_TLDS = frozenset(
    {"cc", "xyz", "top", "vip", "icu", "shop", "club", "online", "site", "live",
     "info", "buzz", "click", "link", "work", "cfd", "sbs", "life", "asia", "me"}
)
URL_SHORTENERS = frozenset(
    {"bit.ly", "tinyurl.com", "t.ly", "cutt.ly", "shorturl.at", "s.id", "rb.gy",
     "is.gd", "t.co", "goo.gl", "ow.ly", "tiny.cc", "shorturl.asia"}
)
MIN_SUBSTRING_BRAND_LENGTH = 5
LURE_WORDS = ("update", "verify", "secure", "login", "confirm", "refund", "account",
              "parcel", "delivery", "tax", "reward", "bonus", "wallet", "otp")


def extract_host(url: str) -> str:
    with_scheme = url if "://" in url else "http://" + url
    return (urlsplit(with_scheme).hostname or "").lower()


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _mimics_brand(host: str) -> bool:
    # Short brands like "scb" only count as a whole label/segment, so that
    # "measure.com" is not mistaken for the "mea" utility brand.
    segments = set(re.split(r"[.\-]", host))
    return any(
        (len(brand) >= MIN_SUBSTRING_BRAND_LENGTH and brand in host) or brand in segments
        for brand in brand_keywords()
    )


def inspect_url(url: str) -> DomainFinding:
    host = extract_host(url)
    if not host or is_official_host(host):
        return DomainFinding(host=host, flags=())

    flags: list[str] = []
    if _is_ip(host):
        flags.append(FLAG_IP_HOST)
    if host in URL_SHORTENERS:
        flags.append(FLAG_SHORTENER)
    if _mimics_brand(host):
        flags.append(FLAG_FAKE_DOMAIN)
    if host.rsplit(".", 1)[-1] in RISKY_TLDS:
        flags.append(FLAG_RISKY_TLD)
    if any(word in host for word in LURE_WORDS):
        flags.append(FLAG_LURE_WORDS)
    if url.lower().startswith("http://"):
        flags.append(FLAG_NOT_HTTPS)
    return DomainFinding(host=host, flags=tuple(flags))


def inspect_urls(urls: tuple[str, ...]) -> tuple[DomainFinding, ...]:
    return tuple(inspect_url(u) for u in urls)
