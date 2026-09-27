"""Named-entity extraction for scam messages.

Regex is used instead of a statistical NER model: phone numbers, URLs and
account numbers have rigid formats, so patterns are faster and deterministic.
"""

import re

from app.models import Entities
from app.nlp.organizations import find_organizations

_ASCII_BOUNDARY = r"(?<![A-Za-z0-9.@/-])"

_URL_PATTERN = re.compile(
    _ASCII_BOUNDARY
    + r"(?:https?://[^\s<>\"']+|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?:/[^\s<>\"']*)?)",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Thai bank account format xxx-x-xxxxx-x, or 10-12 digits after an account keyword.
_ACCOUNT_FORMATTED = re.compile(r"(?<!\d)\d{3}-\d-\d{5}-\d(?!\d)")
_ACCOUNT_WITH_KEYWORD = re.compile(
    r"(?:บัญชี|บช\.?|เลขที่บัญชี|account|acc\.?)\D{0,25}?((?:\d[\s-]?){9,11}\d)(?!\d)",
    re.IGNORECASE,
)

_PHONE_CANDIDATE = re.compile(r"(?<![\d+])(?:\+66|0)[\d\s-]{7,13}\d(?!\d)")
_MOBILE_DIGITS = re.compile(r"^0[689]\d{8}$")
_LANDLINE_DIGITS = re.compile(r"^0[2-7]\d{7}$")

_AMOUNT_PATTERN = re.compile(
    r"(?:฿\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
    r"|(?:(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?\s?(?:บาท|฿|thb)(?![a-z]))",
    re.IGNORECASE,
)

_TRAILING_PUNCTUATION = ".,;:!?)]}'\""


def _unique(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def extract_urls(text: str) -> tuple[str, ...]:
    without_emails = _EMAIL_PATTERN.sub(" ", text)
    urls = [m.group(0).rstrip(_TRAILING_PUNCTUATION) for m in _URL_PATTERN.finditer(without_emails)]
    return _unique([u for u in urls if not _looks_like_decimal(u)])


def _looks_like_decimal(candidate: str) -> bool:
    return bool(re.fullmatch(r"[\d.]+", candidate))


def extract_accounts(text: str) -> tuple[str, ...]:
    found = [m.group(0) for m in _ACCOUNT_FORMATTED.finditer(text)]
    found += [_digits(m.group(1)) for m in _ACCOUNT_WITH_KEYWORD.finditer(text)]
    return _unique([_digits(a) for a in found])


def _normalize_phone(raw: str) -> str | None:
    digits = _digits(raw)
    if digits.startswith("66"):
        digits = "0" + digits[2:]
    if _MOBILE_DIGITS.match(digits) or _LANDLINE_DIGITS.match(digits):
        return digits
    return None


def extract_phones(text: str, exclude: tuple[str, ...] = ()) -> tuple[str, ...]:
    phones = []
    for match in _PHONE_CANDIDATE.finditer(text):
        normalized = _normalize_phone(match.group(0))
        if normalized and normalized not in exclude:
            phones.append(normalized)
    return _unique(phones)


def extract_amounts(text: str) -> tuple[str, ...]:
    amounts = []
    for match in _AMOUNT_PATTERN.finditer(text):
        number = match.group(1) or match.group(2)
        amounts.append(f"{number} บาท")
    return _unique(amounts)


def extract_entities(text: str) -> Entities:
    accounts = extract_accounts(text)
    return Entities(
        phones=extract_phones(text, exclude=accounts),
        urls=extract_urls(text),
        accounts=accounts,
        amounts=extract_amounts(text),
        organizations=tuple(org.name for org in find_organizations(text)),
    )
