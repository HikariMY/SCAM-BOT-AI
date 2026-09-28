import pytest
from linebot.v3.messaging import RichMenuSwitchAction
from PIL import Image

from app.line_handler import CMD_CHECK, CMD_HELP, CMD_IMAGE, CMD_PRIVACY
from scripts.setup_rich_menu import (
    ALIAS_CHECK,
    ALIAS_HOME,
    CHECK_IMAGE,
    HEIGHT,
    HOME_IMAGE,
    TAB_H,
    WIDTH,
    build_check_menu,
    build_home_menu,
)

BASE_URL = "https://scam.example.com"


def area_sum(menu) -> int:
    return sum(a.bounds.width * a.bounds.height for a in menu.areas)


@pytest.mark.parametrize("menu", [build_check_menu(), build_home_menu(BASE_URL)])
def test_menus_fully_cover_image_and_open_by_default(menu):
    assert area_sum(menu) == WIDTH * HEIGHT
    assert menu.selected is True


@pytest.mark.parametrize("menu", [build_check_menu(), build_home_menu(BASE_URL)])
def test_both_menus_have_tabs_to_switch(menu):
    tabs = [a.action for a in menu.areas if a.bounds.y == 0]

    assert all(isinstance(t, RichMenuSwitchAction) for t in tabs)
    assert [t.rich_menu_alias_id for t in tabs] == [ALIAS_CHECK, ALIAS_HOME]
    assert all(a.bounds.height == TAB_H for a in menu.areas if a.bounds.y == 0)


def test_check_menu_keeps_original_big_buttons():
    actions = [a.action for a in build_check_menu().areas if a.bounds.y >= TAB_H]

    assert [getattr(a, "text", None) for a in actions] == [CMD_IMAGE, CMD_CHECK, None, CMD_HELP]
    assert actions[2].uri == "tel:1441"


def test_home_menu_links_dashboard_help_and_privacy():
    actions = [a.action for a in build_home_menu(BASE_URL + "/").areas if a.bounds.y >= TAB_H]

    assert actions[0].text == CMD_CHECK
    assert actions[1].uri == f"{BASE_URL}/dashboard"
    assert [actions[2].text, actions[3].text] == [CMD_HELP, CMD_PRIVACY]


@pytest.mark.parametrize("path", [CHECK_IMAGE, HOME_IMAGE])
def test_menu_images_match_line_requirements(path):
    with Image.open(path) as image:
        assert image.size == (WIDTH, HEIGHT)
    assert path.stat().st_size < 1024 * 1024
