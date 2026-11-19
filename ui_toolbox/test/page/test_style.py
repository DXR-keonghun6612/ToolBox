"""공통 style - 토큰 덮기, palette, style 객체의 토큰 채움."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QPalette

from ui_toolbox.page import Base, Palette, Tokens
from ui_toolbox.page._style import TOKENS


def test_style_flow():
    # 단계 : 토큰 - 기본 위에 덮음
    _t = Tokens(accent="#ff0000")
    assert _t["accent"] == "#ff0000" and _t["bg"] == TOKENS["bg"], "tokens: override on defaults"

    # 단계 : palette - 역할마다 토큰
    _p = Palette(_t)
    assert _p.color(QPalette.ColorRole.Highlight) == QColor("#ff0000"), "palette: Highlight from accent"

    # 단계 : style 객체 - 값의 토큰을 채움
    _b = Base(_t)
    assert _b["Readout"] == {"color": TOKENS["muted"]}, "base: token filled"
    assert all("{" not in _v for _props in _b.values() for _v in _props.values()), "base: no unfilled token"

    # 실패 갈래 : 모르는 토큰
    with pytest.raises(KeyError):
        Tokens(nope="#000")
