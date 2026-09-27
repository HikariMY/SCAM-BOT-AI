from app.nlp.entities import (
    extract_accounts,
    extract_amounts,
    extract_entities,
    extract_phones,
    extract_urls,
)


class TestUrls:
    def test_finds_bare_domain_after_thai_text(self):
        assert extract_urls("อัปเดตภายใน 24 ชม. ที่parcel-th-update.cc") == ("parcel-th-update.cc",)

    def test_finds_full_url_and_strips_trailing_punctuation(self):
        assert extract_urls("กดเลย https://bit.ly/abc123.") == ("https://bit.ly/abc123",)

    def test_ignores_email_addresses(self):
        assert extract_urls("ติดต่อ admin@example.com") == ()

    def test_ignores_decimal_numbers(self):
        assert extract_urls("ราคา 12.50 บาท") == ()

    def test_deduplicates(self):
        assert extract_urls("scb-th.xyz และ scb-th.xyz") == ("scb-th.xyz",)


class TestPhones:
    def test_mobile_with_dashes(self):
        assert extract_phones("โทร 089-123-4567 ด่วน") == ("0891234567",)

    def test_international_prefix_is_normalized(self):
        assert extract_phones("call +66 81 234 5678") == ("0812345678",)

    def test_bangkok_landline(self):
        assert extract_phones("ติดต่อ 02-123-4567") == ("021234567",)

    def test_hotline_short_code_is_not_a_phone(self):
        assert extract_phones("แจ้ง 1441") == ()

    def test_excludes_numbers_already_classified_as_accounts(self):
        assert extract_phones("บัญชี 0891234567", exclude=("0891234567",)) == ()


class TestAccounts:
    def test_thai_bank_format(self):
        assert extract_accounts("โอนเข้า 123-4-56789-0") == ("1234567890",)

    def test_digits_after_account_keyword(self):
        assert extract_accounts("เลขที่บัญชี: 9876543210") == ("9876543210",)

    def test_plain_number_without_keyword_is_not_account(self):
        assert extract_accounts("รหัสสินค้า 9876543210") == ()


class TestAmounts:
    def test_baht_suffix_with_commas(self):
        assert extract_amounts("ค่าธรรมเนียม 1,500 บาท") == ("1,500 บาท",)

    def test_baht_sign_prefix(self):
        assert extract_amounts("ชำระ ฿350 ด่วน") == ("350 บาท",)


def test_extract_entities_combines_all_extractors():
    entities = extract_entities(
        "ธนาคารกสิกรไทย: บัญชีถูกระงับ โอน 2,000 บาท เข้า 123-4-56789-0 โทร 0812345678 kbank-verify.top"
    )

    assert entities.accounts == ("1234567890",)
    assert entities.phones == ("0812345678",)
    assert entities.amounts == ("2,000 บาท",)
    assert entities.urls == ("kbank-verify.top",)
    assert entities.organizations == ("ธนาคารกสิกรไทย",)
