"""Settings loaded from environment variables (and `.env` for local runs)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
DEFAULT_DATABASE_PATH = "data/scam_alert.db"
TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    line_channel_secret: str | None
    line_channel_access_token: str | None
    database_path: str
    seed_demo_if_empty: bool = False

    @property
    def line_enabled(self) -> bool:
        return bool(self.line_channel_secret and self.line_channel_access_token)


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        gemini_api_key=_optional("GEMINI_API_KEY"),
        gemini_model=_optional("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
        line_channel_secret=_optional("LINE_CHANNEL_SECRET"),
        line_channel_access_token=_optional("LINE_CHANNEL_ACCESS_TOKEN"),
        database_path=_optional("DATABASE_PATH") or DEFAULT_DATABASE_PATH,
        seed_demo_if_empty=(_optional("SEED_DEMO_IF_EMPTY") or "").lower() in TRUTHY,
    )
