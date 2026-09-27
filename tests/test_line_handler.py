import base64
import hashlib
import hmac
import json

import pytest
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import FlexMessage, TextMessage

from app import formatter
from app.analyzer import MSG_IMAGE_NEEDS_AI, ScamAnalyzer
from app.line_flex import DETAILS_POSTBACK_PREFIX, FlexReply
from app.line_handler import (
    CMD_CHECK,
    CMD_HELP,
    CMD_HOTLINE,
    CMD_IMAGE,
    CMD_STATS,
    LineBot,
    to_line_message,
)
from app.models import ScamCategory, Verdict
from app.repository import ReportRepository

SECRET = "test-secret"
SLIDE_TEXT = "พัสดุของท่านจัดส่งไม่ได้ เนื่องจากที่อยู่ไม่ครบ กรุณาอัปเดตภายใน 24 ชม. ที่ parcel-th-update.cc"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class FakeVisionLLM:
    name = "fake"

    def classify(self, text, entities, findings):
        return Verdict(ScamCategory.PHISHING, 90, ("เร่งเวลา",), "หลอกกดลิงก์", "ขนส่ง")

    def extract_text(self, image, mime_type):
        return SLIDE_TEXT


class RecordingBot(LineBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent: list[tuple[str, list]] = []
        self.loading_for: list[str] = []

    def _reply(self, reply_token, replies):
        self.sent.append((reply_token, replies))

    def _show_loading(self, user_id):
        self.loading_for.append(user_id)

    def _download_content(self, message_id):
        return PNG_BYTES


@pytest.fixture
def repo(tmp_path):
    return ReportRepository(str(tmp_path / "line.db"))


@pytest.fixture
def bot(repo):
    return RecordingBot(SECRET, "token", ScamAnalyzer(), repo)


@pytest.fixture
def vision_bot(repo):
    return RecordingBot(SECRET, "token", ScamAnalyzer(FakeVisionLLM()), repo)


def sign(body: str) -> str:
    digest = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def webhook_body(event: dict) -> str:
    base = {
        "timestamp": 1790000000000,
        "source": {"type": "user", "userId": "U123"},
        "webhookEventId": "01TEST",
        "deliveryContext": {"isRedelivery": False},
        "mode": "active",
    }
    return json.dumps({"destination": "Ubot", "events": [base | event]}, ensure_ascii=False)


def text_event(text: str) -> dict:
    return {"type": "message", "replyToken": "reply-1",
            "message": {"type": "text", "id": "m1", "text": text, "quoteToken": "q"}}


def image_event() -> dict:
    return {"type": "message", "replyToken": "reply-img",
            "message": {"type": "image", "id": "m2", "quoteToken": "q",
                        "contentProvider": {"type": "line"}}}


def test_text_message_gets_flex_card_and_is_saved(bot, repo):
    body = webhook_body(text_event(SLIDE_TEXT))

    bot.handle(body, sign(body))

    token, replies = bot.sent[0]
    assert token == "reply-1"
    assert isinstance(replies[0], FlexReply)
    assert replies[0].alt_text.startswith("🔴")
    assert repo.count() == 1
    assert bot.loading_for == ["U123"]


def test_forged_signature_is_rejected(bot):
    body = webhook_body(text_event(SLIDE_TEXT))

    with pytest.raises(InvalidSignatureError):
        bot.handle(body, "forged")


def test_follow_event_gets_welcome(bot):
    body = webhook_body({"type": "follow", "replyToken": "reply-2", "follow": {"isUnblocked": False}})

    bot.handle(body, sign(body))

    assert bot.sent == [("reply-2", [formatter.WELCOME_TEXT])]


def test_image_is_read_and_analyzed(vision_bot, repo):
    body = webhook_body(image_event())

    vision_bot.handle(body, sign(body))

    reply = vision_bot.sent[0][1][0]
    assert isinstance(reply, FlexReply)
    assert repo.count() == 1


def test_image_without_ai_explains_how_to_send_text(bot, repo):
    assert bot.reply_for_image("m2") == [MSG_IMAGE_NEEDS_AI]
    assert repo.count() == 0


def test_sticker_message_is_unsupported(bot):
    body = webhook_body({"type": "message", "replyToken": "reply-3",
                         "message": {"type": "sticker", "id": "m3", "quoteToken": "q",
                                     "packageId": "1", "stickerId": "1",
                                     "stickerResourceType": "STATIC"}})

    bot.handle(body, sign(body))

    assert bot.sent == [("reply-3", [formatter.UNSUPPORTED_TEXT])]


def test_details_postback_returns_stored_report(bot):
    code = bot.reply_for_text(SLIDE_TEXT)[0].contents["footer"]["contents"][1]["action"]["data"]
    body = webhook_body({"type": "postback", "replyToken": "reply-4", "postback": {"data": code}})

    bot.handle(body, sign(body))

    details = bot.sent[0][1][0]
    assert details.startswith("รายละเอียดรายงาน SA-")
    assert "parcel-th-update[.]cc" in details


def test_details_postback_for_unknown_report(bot):
    assert bot.reply_for_postback(f"{DETAILS_POSTBACK_PREFIX}SA-1999-0001") == [
        formatter.DETAILS_NOT_FOUND_TEXT
    ]
    assert bot.reply_for_postback("other=1") == []


@pytest.mark.parametrize(("command", "expected"), [
    (CMD_CHECK, formatter.ASK_FOR_MESSAGE_TEXT),
    (CMD_IMAGE, formatter.ASK_FOR_IMAGE_TEXT),
    (CMD_HELP, formatter.HELP_TEXT),
    (CMD_HOTLINE, formatter.HOTLINE_TEXT),
])
def test_menu_commands(bot, repo, command, expected):
    assert bot.reply_for_text(command) == [expected]
    assert repo.count() == 0


def test_stats_command(bot):
    bot.reply_for_text(SLIDE_TEXT)

    assert "ตรวจทั้งหมด 1 ข้อความ" in bot.reply_for_text(CMD_STATS)[0]


def test_short_text_is_not_analyzed(bot, repo):
    assert bot.reply_for_text("สวัสดี") == [formatter.TOO_SHORT_TEXT]
    assert repo.count() == 0


def test_short_text_with_link_is_analyzed(bot, repo):
    bot.reply_for_text("bit.ly/x1")

    assert repo.count() == 1


def test_reply_failure_does_not_raise(repo):
    class FailingReplyBot(RecordingBot):
        def _reply(self, reply_token, replies):
            raise ConnectionError("LINE API down")

    bot = FailingReplyBot(SECRET, "token", ScamAnalyzer(), repo)
    body = webhook_body(text_event(SLIDE_TEXT))

    bot.handle(body, sign(body))

    assert repo.count() == 1


def test_analysis_failure_returns_error_message(repo):
    class BrokenAnalyzer(ScamAnalyzer):
        def analyze(self, text):
            raise RuntimeError("boom")

        def analyze_image(self, image):
            raise RuntimeError("boom")

    bot = RecordingBot(SECRET, "token", BrokenAnalyzer(), repo)

    assert bot.reply_for_text(SLIDE_TEXT) == [formatter.ERROR_TEXT]
    assert bot.reply_for_image("m1") == [formatter.ERROR_TEXT]


def test_line_messages_get_quick_reply_only_when_last(bot):
    card = bot.reply_for_text(SLIDE_TEXT)[0]

    flex = to_line_message(card, with_quick_reply=True)
    text = to_line_message("hello", with_quick_reply=False)

    assert isinstance(flex, FlexMessage) and flex.quick_reply is not None
    assert isinstance(text, TextMessage) and text.quick_reply is None
