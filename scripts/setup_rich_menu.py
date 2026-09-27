"""Create the big-button LINE rich menu and make it the default for all users.

Usage (after filling LINE_CHANNEL_ACCESS_TOKEN in .env):
    python -m scripts.setup_rich_menu            # create/replace the menu
    python -m scripts.setup_rich_menu --dry-run  # print the menu without calling LINE

Run once per channel. Re-running replaces the previous menu with the same name.
"""

import argparse
import json
from pathlib import Path

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessageAction,
    MessagingApi,
    MessagingApiBlob,
    RichMenuArea,
    RichMenuBounds,
    RichMenuRequest,
    RichMenuSize,
    URIAction,
)

from app.advice import HOTLINE
from app.config import load_settings
from app.line_handler import CMD_CHECK, CMD_HELP, CMD_IMAGE

MENU_NAME = "scam-alert-main"
IMAGE_PATH = Path(__file__).parent / "rich_menu" / "rich_menu.png"
WIDTH, HEIGHT = 2500, 1686
HALF_W, HALF_H = WIDTH // 2, HEIGHT // 2


def build_menu() -> RichMenuRequest:
    def area(x: int, y: int, action) -> RichMenuArea:
        return RichMenuArea(bounds=RichMenuBounds(x=x, y=y, width=HALF_W, height=HALF_H), action=action)

    return RichMenuRequest(
        size=RichMenuSize(width=WIDTH, height=HEIGHT),
        selected=True,  # open by default so elderly users see the buttons immediately
        name=MENU_NAME,
        chat_bar_text="เปิดเมนู",
        areas=[
            area(0, 0, MessageAction(label="ส่งรูปให้ตรวจ", text=CMD_IMAGE)),
            area(HALF_W, 0, MessageAction(label="ตรวจข้อความ", text=CMD_CHECK)),
            area(0, HALF_H, URIAction(label=f"โทร {HOTLINE}", uri=f"tel:{HOTLINE}")),
            area(HALF_W, HALF_H, MessageAction(label="วิธีใช้", text=CMD_HELP)),
        ],
    )


def install(access_token: str, menu: RichMenuRequest) -> str:
    image = IMAGE_PATH.read_bytes()
    with ApiClient(Configuration(access_token=access_token)) as client:
        api, blob = MessagingApi(client), MessagingApiBlob(client)
        for old in api.get_rich_menu_list().richmenus:
            if old.name == MENU_NAME:
                api.delete_rich_menu(old.rich_menu_id)
        menu_id = api.create_rich_menu(menu).rich_menu_id
        blob.set_rich_menu_image(menu_id, body=bytearray(image), _headers={"Content-Type": "image/png"})
        api.set_default_rich_menu(menu_id)
    return menu_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    menu = build_menu()
    if args.dry_run:
        print(json.dumps(menu.to_dict(), ensure_ascii=False, indent=2))
        return
    token = load_settings().line_channel_access_token
    if not token:
        raise SystemExit("LINE_CHANNEL_ACCESS_TOKEN is not set in .env")
    print(f"Rich menu installed: {install(token, menu)}")


if __name__ == "__main__":
    main()
