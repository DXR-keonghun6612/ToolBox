"""공통 style - 토큰 하나에서 palette 와 style 객체가 나옴.

- 토큰은 `이름 -> 값` 맵. 안 준 이름은 `TOKENS` 기본, 모르는 이름은 실패
- palette 는 앱에 한 번(`app.Run`), style 객체는 root 의 `Fill` 에 `style` 로(`Main`)
- `RULES` 의 값 글자 `{이름}` 은 토큰으로 채움
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor, QPalette

__all__ = ["PALETTE", "RULES", "TOKENS", "Base", "Palette", "Tokens"]

#: 기본 토큰.
TOKENS: dict[str, Any] = {
    "bg": "#2d2d2d",        "fg": "#dcdcdc",
    "field_bg": "#1e1e1e",  "field_alt_bg": "#282828",
    "tip_bg": "#323232",    "control_bg": "#3c3c3c",
    "accent": "#2a82da",    "accent_fg": "#000000",
    "warn": "#ff5050",      "muted": "#888888",
    "surface": "#1a1a1a",   "border": "#333333",
}

#: `QPalette` 역할 -> 토큰 이름.
PALETTE: dict[str, str] = {
    "Window": "bg",           "WindowText": "fg",
    "Base": "field_bg",       "AlternateBase": "field_alt_bg",
    "ToolTipBase": "tip_bg",  "ToolTipText": "fg",
    "Text": "fg",             "Button": "control_bg",
    "ButtonText": "fg",       "BrightText": "warn",
    "Highlight": "accent",    "HighlightedText": "accent_fg",
}

#: 공통 style - selector -> 속성. 값의 `{이름}` 은 토큰.
RULES: dict[str, dict[str, str]] = {
    "Readout": {"color": "{muted}"},
    "Fold QToolButton": {"text-align": "left", "font-weight": "bold", "border": "none"},
    'QSlider[empty="true"]::handle:horizontal': {"background": "{muted}"},
    "Raster_editor QGraphicsView": {"background": "{surface}", "border": "1px solid {border}"},
}


def Tokens(**over: Any) -> dict[str, Any]:
    """기본 토큰 위에 `over` 를 덮은 사본.

    Raises:
        KeyError: 모르는 토큰 이름일 때.
    """
    _unknown = sorted(set(over) - set(TOKENS))
    if _unknown:
        raise KeyError(f"unknown tokens {_unknown} - known {sorted(TOKENS)}")
    return {**TOKENS, **over}


def Palette(tokens: dict[str, Any]) -> QPalette:
    """토큰 -> `QPalette`."""
    _p = QPalette()
    for _role, _name in PALETTE.items():
        _p.setColor(getattr(QPalette.ColorRole, _role), QColor(tokens[_name]))
    return _p


def Base(tokens: dict[str, Any]) -> dict[str, dict[str, str]]:
    """토큰 -> 공통 style 객체. `Fill` 의 `style` 로 씀."""
    return {_sel: {_k: _v.format(**tokens) for _k, _v in _props.items()} for _sel, _props in RULES.items()}
