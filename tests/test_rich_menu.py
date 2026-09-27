from PIL import Image

from app.line_handler import CMD_CHECK, CMD_HELP, CMD_IMAGE
from scripts.setup_rich_menu import HEIGHT, IMAGE_PATH, WIDTH, build_menu


def test_menu_has_four_big_buttons_covering_the_image():
    menu = build_menu()

    bounds = [(a.bounds.x, a.bounds.y, a.bounds.width, a.bounds.height) for a in menu.areas]
    assert sum(w * h for _, _, w, h in bounds) == WIDTH * HEIGHT
    assert menu.selected is True


def test_menu_buttons_trigger_bot_commands_and_call():
    actions = [a.action for a in build_menu().areas]

    assert [a.text for a in actions if hasattr(a, "text")] == [CMD_IMAGE, CMD_CHECK, CMD_HELP]
    assert any(getattr(a, "uri", "") == "tel:1441" for a in actions)


def test_menu_image_matches_line_requirements():
    with Image.open(IMAGE_PATH) as image:
        assert image.size == (WIDTH, HEIGHT)
    assert IMAGE_PATH.stat().st_size < 1024 * 1024
