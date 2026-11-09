"""치수는 위젯이 안 듦 - 코드가 토큰을 읽음.

박아 두면 테마가 못 바꿈. `Use()` 로 갈아끼운 값이 새로 짓는 위젯에 나타나야 함.
"""

from __future__ import annotations

import pytest

from ui_toolbox.field import Button, Field
from ui_toolbox.field.form.widget import Button_bar, Int_slider_row
from ui_toolbox.style import DEFAULT, Style, Use


@pytest.fixture
def _restore():
    """토큰은 전역 - 만진 뒤 되돌림."""
    yield
    Use(Style())


def test_default_spacing_is_the_gap_token():
    assert Int_slider_row("i", 0, 10, 3).layout().spacing() == DEFAULT["gap"]


def test_spacing_follows_the_token(_restore):
    Use(Style(gap=17))
    assert Int_slider_row("i", 0, 10, 3).layout().spacing() == 17


def test_readout_width_follows_the_token(_restore):
    Use(Style(compact_width=77))
    _w = Int_slider_row("s", 0, 10, 0, readout=True)
    assert _w._slider.maximumWidth() == 77


def test_stretching_slider_has_no_fixed_width():
    _w = Int_slider_row("i", 0, 10, 3)
    assert _w._slider.maximumWidth() > DEFAULT["compact_width"]


def test_button_size_follows_the_token(_restore):
    Use(Style(button=33))
    _bar = Button_bar([Button("x", "툴팁")])
    assert _bar._buttons[0].maximumWidth() == 33


def test_field_width_stays_with_the_declaration():
    """칸마다 다른 폭은 선언 소유 - 테마가 못 정함."""
    assert Field("k", width=140).width == 140
