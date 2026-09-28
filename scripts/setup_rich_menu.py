"""Create the two tabbed LINE rich menus and make the big-button one the default.

- "ตรวจข้อความ" tab: four big buttons for elderly users (default)
- "เมนูหลัก" tab: start checking, Dashboard, how-to and privacy

Users switch between them with the tab bar at the top (rich menu aliases).

Usage (after filling LINE_CHANNEL_ACCESS_TOKEN and PUBLIC_BASE_URL in .env):
    python -m scripts.setup_rich_menu            # create/replace both menus
    python -m scripts.setup_rich_menu --dry-run  # print the menus without calling LINE

Re-running replaces the previous menus.
"""

import argparse
import json
import os
from pathlib import Path

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    CreateRichMenuAliasRequest,
    MessageAction,
    MessagingApi,
    MessagingApiBlob,
    RichMenuArea,
    RichMenuBounds,
    RichMenuRequest,
    RichMenuSize,
    RichMenuSwitchAction,
    UpdateRichMenuAliasRequest,
    URIAction,
)

from app.advice import HOTLINE
from app.config import load_settings
from app.line_handler import CMD_CHECK, CMD_HELP, CMD_IMAGE, CMD_PRIVACY

IMAGE_DIR = Path(__file__).parent / "rich_menu"
CHECK_IMAGE = IMAGE_DIR / "rich_menu_check.png"
HOME_IMAGE = IMAGE_DIR / "rich_menu_home.png"

WIDTH, HEIGHT = 2500, 1686
HALF_W = WIDTH // 2
# Must match scripts/rich_menu/rich_menu.html (CSS pixels x2).
TAB_H = 250
CONTENT_H = HEIGHT - TAB_H
HERO_BOTTOM = 1070
CARD_W = (833, 834, 833)

CHECK_NAME, HOME_NAME = "scam-alert-check", "scam-alert-home"
MANAGED_NAMES = {CHECK_NAME, HOME_NAME, "scam-alert-main"}  # "scam-alert-main" = first version
ALIAS_CHECK, ALIAS_HOME = "scam-check", "scam-home"
PLACEHOLDER_BASE_URL = "https://example.com"


def _area(x: int, y: int, width: int, height: int, action) -> RichMenuArea:
    return RichMenuArea(bounds=RichMenuBounds(x=x, y=y, width=width, height=height), action=action)


def _tab_areas() -> list[RichMenuArea]:
    return [
        _area(0, 0, HALF_W, TAB_H,
              RichMenuSwitchAction(label="ตรวจข้อความ", rich_menu_alias_id=ALIAS_CHECK, data="tab=check")),
        _area(HALF_W, 0, WIDTH - HALF_W, TAB_H,
              RichMenuSwitchAction(label="เมนูหลัก", rich_menu_alias_id=ALIAS_HOME, data="tab=home")),
    ]


def _menu(name: str, areas: list[RichMenuArea]) -> RichMenuRequest:
    return RichMenuRequest(
        size=RichMenuSize(width=WIDTH, height=HEIGHT),
        selected=True,  # open by default so elderly users see the buttons immediately
        name=name,
        chat_bar_text="เปิดเมนู",
        areas=_tab_areas() + areas,
    )


def build_check_menu() -> RichMenuRequest:
    row_h = CONTENT_H // 2
    bottom_y = TAB_H + row_h
    return _menu(CHECK_NAME, [
        _area(0, TAB_H, HALF_W, row_h, MessageAction(label="ส่งรูปให้ตรวจ", text=CMD_IMAGE)),
        _area(HALF_W, TAB_H, HALF_W, row_h, MessageAction(label="ตรวจข้อความ", text=CMD_CHECK)),
        _area(0, bottom_y, HALF_W, HEIGHT - bottom_y, URIAction(label=f"โทร {HOTLINE}", uri=f"tel:{HOTLINE}")),
        _area(HALF_W, bottom_y, HALF_W, HEIGHT - bottom_y, MessageAction(label="วิธีใช้", text=CMD_HELP)),
    ])


def build_home_menu(base_url: str) -> RichMenuRequest:
    card_y, card_h = HERO_BOTTOM, HEIGHT - HERO_BOTTOM
    x1, x2 = CARD_W[0], CARD_W[0] + CARD_W[1]
    return _menu(HOME_NAME, [
        _area(0, TAB_H, WIDTH, HERO_BOTTOM - TAB_H, MessageAction(label="เริ่มตรวจสอบ", text=CMD_CHECK)),
        _area(0, card_y, CARD_W[0], card_h,
              URIAction(label="Dashboard", uri=f"{base_url.rstrip('/')}/dashboard")),
        _area(x1, card_y, CARD_W[1], card_h, MessageAction(label="วิธีใช้งาน", text=CMD_HELP)),
        _area(x2, card_y, CARD_W[2], card_h, MessageAction(label="ความเป็นส่วนตัว", text=CMD_PRIVACY)),
    ])


def _create(api: MessagingApi, blob: MessagingApiBlob, menu: RichMenuRequest, image: Path) -> str:
    menu_id = api.create_rich_menu(menu).rich_menu_id
    blob.set_rich_menu_image(menu_id, body=bytearray(image.read_bytes()),
                             _headers={"Content-Type": "image/png"})
    return menu_id


def _point_alias(api: MessagingApi, alias_id: str, menu_id: str) -> None:
    existing = {a.rich_menu_alias_id for a in api.get_rich_menu_alias_list().aliases}
    if alias_id in existing:
        api.update_rich_menu_alias(alias_id, UpdateRichMenuAliasRequest(rich_menu_id=menu_id))
    else:
        api.create_rich_menu_alias(CreateRichMenuAliasRequest(rich_menu_alias_id=alias_id, rich_menu_id=menu_id))


def install(access_token: str, base_url: str) -> tuple[str, str]:
    with ApiClient(Configuration(access_token=access_token)) as client:
        api, blob = MessagingApi(client), MessagingApiBlob(client)
        old_ids = [m.rich_menu_id for m in api.get_rich_menu_list().richmenus if m.name in MANAGED_NAMES]
        check_id = _create(api, blob, build_check_menu(), CHECK_IMAGE)
        home_id = _create(api, blob, build_home_menu(base_url), HOME_IMAGE)
        _point_alias(api, ALIAS_CHECK, check_id)
        _point_alias(api, ALIAS_HOME, home_id)
        api.set_default_rich_menu(check_id)
        # Delete old menus only after the new ones are live, so users never see an empty chat bar.
        for menu_id in old_ids:
            api.delete_rich_menu(menu_id)
    return check_id, home_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-url", help="public site URL, e.g. https://xxx.onrender.com "
                                           "(default: PUBLIC_BASE_URL in .env)")
    args = parser.parse_args()

    settings = load_settings()  # also loads .env into the environment
    base_url = args.base_url or os.getenv("PUBLIC_BASE_URL", "").strip()
    if args.dry_run:
        menus = [build_check_menu(), build_home_menu(base_url or PLACEHOLDER_BASE_URL)]
        print(json.dumps([m.to_dict() for m in menus], ensure_ascii=False, indent=2))
        return
    if not settings.line_channel_access_token:
        raise SystemExit("LINE_CHANNEL_ACCESS_TOKEN is not set in .env")
    if not base_url.startswith("https://"):
        raise SystemExit("Set PUBLIC_BASE_URL in .env (or --base-url) to your https:// site for the Dashboard button")
    check_id, home_id = install(settings.line_channel_access_token, base_url)
    print(f"Rich menus installed. check={check_id} home={home_id}")


if __name__ == "__main__":
    main()
