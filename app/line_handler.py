"""LINE Messaging API webhook handling."""

import logging
from dataclasses import replace

from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    ApiClient,
    CameraAction,
    CameraRollAction,
    Configuration,
    FlexContainer,
    FlexMessage,
    MessageAction,
    MessagingApi,
    MessagingApiBlob,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    ImageMessageContent,
    MessageEvent,
    PostbackEvent,
    TextMessageContent,
)

from app import formatter
from app.analyzer import ImageAnalysisError, ScamAnalyzer
from app.line_flex import DETAILS_POSTBACK_PREFIX, FlexReply, verdict_reply
from app.models import AnalysisResult
from app.nlp.entities import extract_urls
from app.repository import ReportRepository

logger = logging.getLogger(__name__)

MIN_ANALYZE_LENGTH = 12
MAX_LINE_MESSAGES = 5
LOADING_SECONDS = 20

CMD_CHECK = "ตรวจข้อความ"
CMD_IMAGE = "ส่งรูปให้ตรวจ"
CMD_HELP = "วิธีใช้"
CMD_HOTLINE = "สายด่วน 1441"
CMD_STATS = "สถิติกลโกง"

Reply = str | FlexReply


def quick_reply() -> QuickReply:
    return QuickReply(items=[
        QuickReplyItem(action=CameraRollAction(label="📷 ส่งรูปให้ตรวจ")),
        QuickReplyItem(action=CameraAction(label="📸 ถ่ายรูป")),
        QuickReplyItem(action=MessageAction(label="✍️ ตรวจข้อความ", text=CMD_CHECK)),
        QuickReplyItem(action=MessageAction(label="☎️ สายด่วน 1441", text=CMD_HOTLINE)),
        QuickReplyItem(action=MessageAction(label="❓ วิธีใช้", text=CMD_HELP)),
        QuickReplyItem(action=MessageAction(label="📊 สถิติกลโกง", text=CMD_STATS)),
    ])


def to_line_message(reply: Reply, with_quick_reply: bool):
    extra = {"quick_reply": quick_reply()} if with_quick_reply else {}
    if isinstance(reply, FlexReply):
        return FlexMessage(alt_text=reply.alt_text,
                           contents=FlexContainer.from_dict(reply.contents), **extra)
    return TextMessage(text=reply, **extra)


class LineBot:
    def __init__(self, channel_secret: str, access_token: str,
                 analyzer: ScamAnalyzer, repository: ReportRepository) -> None:
        self._parser = WebhookParser(channel_secret)
        self._configuration = Configuration(access_token=access_token)
        self._analyzer = analyzer
        self._repository = repository

    def handle(self, body: str, signature: str) -> None:
        """Parse and answer a webhook call. Raises InvalidSignatureError on forged requests."""
        for event in self._parser.parse(body, signature):
            if isinstance(event, MessageEvent):
                self._show_loading(getattr(event.source, "user_id", None))
            replies = self.reply_for_event(event)
            if not replies or not getattr(event, "reply_token", None):
                continue
            try:
                self._reply(event.reply_token, replies)
            except Exception:
                # Answer 200 anyway: LINE would redeliver and the reply token is single-use.
                logger.exception("Failed to send LINE reply")

    def reply_for_event(self, event) -> list[Reply]:
        if isinstance(event, FollowEvent):
            return [formatter.WELCOME_TEXT]
        if isinstance(event, PostbackEvent):
            return self.reply_for_postback(event.postback.data)
        if not isinstance(event, MessageEvent):
            return []
        if isinstance(event.message, TextMessageContent):
            return self.reply_for_text(event.message.text)
        if isinstance(event.message, ImageMessageContent):
            return self.reply_for_image(event.message.id)
        return [formatter.UNSUPPORTED_TEXT]

    def reply_for_text(self, text: str) -> list[Reply]:
        command = text.strip()
        fixed = {
            CMD_CHECK: formatter.ASK_FOR_MESSAGE_TEXT,
            CMD_IMAGE: formatter.ASK_FOR_IMAGE_TEXT,
            CMD_HELP: formatter.HELP_TEXT,
            CMD_HOTLINE: formatter.HOTLINE_TEXT,
        }
        if command in fixed:
            return [fixed[command]]
        if command == CMD_STATS:
            return [formatter.format_stats(self._repository.stats("day"))]
        if len(command) < MIN_ANALYZE_LENGTH and not extract_urls(command):
            return [formatter.TOO_SHORT_TEXT]
        try:
            return self._save_and_reply(self._analyzer.analyze(command), command)
        except Exception:
            logger.exception("Failed to analyze LINE text message")
            return [formatter.ERROR_TEXT]

    def reply_for_image(self, message_id: str) -> list[Reply]:
        try:
            result = self._analyzer.analyze_image(self._download_content(message_id))
            return self._save_and_reply(result, result.extracted_text or "")
        except ImageAnalysisError as exc:
            return [str(exc)]
        except Exception:
            logger.exception("Failed to analyze LINE image message")
            return [formatter.ERROR_TEXT]

    def reply_for_postback(self, data: str) -> list[Reply]:
        if not data.startswith(DETAILS_POSTBACK_PREFIX):
            return []
        record = self._repository.get(data.removeprefix(DETAILS_POSTBACK_PREFIX))
        return [formatter.format_details(record) if record else formatter.DETAILS_NOT_FOUND_TEXT]

    def _save_and_reply(self, result: AnalysisResult, text: str) -> list[Reply]:
        code = self._repository.save(result, text, source="line")
        return [verdict_reply(replace(result, report_code=code))]

    def _download_content(self, message_id: str) -> bytes:
        with ApiClient(self._configuration) as client:
            return bytes(MessagingApiBlob(client).get_message_content(message_id))

    def _show_loading(self, user_id: str | None) -> None:
        """Show LINE's typing indicator so users know the bot is working."""
        if not user_id:
            return
        try:
            with ApiClient(self._configuration) as client:
                MessagingApi(client).show_loading_animation(
                    ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=LOADING_SECONDS)
                )
        except Exception:
            logger.warning("Could not show loading animation", exc_info=True)

    def _reply(self, reply_token: str, replies: list[Reply]) -> None:
        replies = replies[:MAX_LINE_MESSAGES]
        messages = [to_line_message(r, with_quick_reply=i == len(replies) - 1)
                    for i, r in enumerate(replies)]
        with ApiClient(self._configuration) as client:
            MessagingApi(client).reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=messages)
            )
