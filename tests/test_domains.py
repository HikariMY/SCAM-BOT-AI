from app.nlp import domains
from app.nlp.domains import extract_host, inspect_url


def test_extract_host_without_scheme():
    assert extract_host("Parcel-TH-Update.cc/track?id=1") == "parcel-th-update.cc"


def test_official_domain_has_no_flags():
    assert inspect_url("https://www.kasikornbank.com/th").flags == ()


def test_official_subdomain_has_no_flags():
    assert inspect_url("https://track.thailandpost.co.th").flags == ()


def test_lookalike_brand_domain_is_flagged():
    finding = inspect_url("kerry-express-th.xyz")

    assert domains.FLAG_FAKE_DOMAIN in finding.flags
    assert domains.FLAG_RISKY_TLD in finding.flags


def test_short_brand_only_matches_whole_segment():
    assert domains.FLAG_FAKE_DOMAIN in inspect_url("scb-secure.net").flags
    assert domains.FLAG_FAKE_DOMAIN not in inspect_url("measure.com").flags


def test_shortener_is_flagged():
    assert domains.FLAG_SHORTENER in inspect_url("https://bit.ly/x").flags


def test_ip_host_and_plain_http_are_flagged():
    flags = inspect_url("http://203.0.113.9/login").flags

    assert domains.FLAG_IP_HOST in flags
    assert domains.FLAG_NOT_HTTPS in flags


def test_unknown_neutral_domain_is_not_suspicious():
    assert not inspect_url("https://example.com").is_suspicious
