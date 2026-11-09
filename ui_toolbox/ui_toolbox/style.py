"""스타일 - 토큰과 역할과 시트.

- 위젯은 자기 `역할`만 표시. 색도 치수도 모름
- 토큰은 `이름 -> 값` dict 하나. 색이 늘어도 선언이 한 줄 늚
- 팔레트도 시트도 그 토큰에서 나옴. 색이 두 곳에 안 삶
- 규칙은 `역할 -> 속성 틀`. 역할이 늘어도 코드가 아니라 표가 늚
- 레이아웃 간격 · 여백은 QSS 로 못 걸어 코드가 토큰을 읽음

값을 안 주면 기본이 남고, 기본에도 없으면 Qt 가 정한다.

아무것도 안 봄 - 개념들이 이것을 보는 것이 유일한 방향.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

__all__ = ["DEFAULT", "HEADER", "LABEL", "MUTED", "READOUT", "RULES", "SECTION",
           "SURFACE", "VALUE", "Mark", "Now", "Palette", "Sheet", "Style", "Use"]

#: 역할을 담는 Qt 속성 이름.
ROLE = "role"

#: 역할 이름 - 위젯이 표시하고 규칙이 받음.
MUTED   = "muted"      # 흐린 글자
HEADER  = "header"     # 칸 머리글
READOUT = "readout"    # 읽기 전용 값
SURFACE = "surface"    # 그림이 놓이는 바닥
SECTION = "section"    # 접히는 묶음의 머리
LABEL   = "label"      # 폼 라벨 칸
VALUE   = "value"      # 폼 값 칸

#: 기본 토큰. 선언이 낱개로 덮음.
DEFAULT: dict[str, Any] = {
    # 창 - 팔레트가 씀
    "bg": "#2d2d2d",        "fg": "#dcdcdc",
    "field_bg": "#1e1e1e",  "field_alt_bg": "#282828",
    "tip_bg": "#323232",    "control_bg": "#3c3c3c",
    "accent": "#2a82da",    "accent_fg": "#000000",
    "warn": "#ff5050",
    # 역할 - 시트가 씀
    "muted": "#888888",     "surface": "#1a1a1a",   "border": "#333333",
    "small": 11,            "label_width": 240,     "value_width": 80,
    # 치수 - 코드가 읽음
    "button": 22,           "tall_button": 30,
    "gap": 4,               "tight": 2,
    "compact_width": 110,
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

#: 역할 -> 속성 틀. 틀의 `{이름}` 은 토큰으로 채워짐.
RULES: dict[str, str] = {
    MUTED:   "color: {muted};",
    HEADER:  "color: {muted}; font-size: {small}px;",
    READOUT: "color: {muted};",
    SURFACE: "background: {surface}; border: 1px solid {border};",
    SECTION: "text-align: left; padding: 3px {gap}px; font-weight: bold; border: none;",
    LABEL:   "min-width: {label_width}px; max-width: {label_width}px;",
    VALUE:   "min-width: {value_width}px; max-width: {value_width}px;",
}


class Style:
    """토큰 묶음. 안 준 이름은 기본에서 온다."""

    def __init__(self, **tokens: Any) -> None:
        """Args:
        **tokens: 덮을 토큰. 이름은 `DEFAULT` 의 것.
        """
        self._tokens = {**DEFAULT, **tokens}

    def __getitem__(self, name: str) -> Any:
        return self._tokens[name]

    def get(self, name: str, default: Any = None) -> Any:
        """그 토큰 (없으면 `default`)."""
        return self._tokens.get(name, default)

    def tokens(self) -> dict[str, Any]:
        """토큰 전부 (사본)."""
        return dict(self._tokens)


_CURRENT = Style()


def Now() -> Style:
    """지금 토큰. 레이아웃 치수를 코드가 읽는 길."""
    return _CURRENT


def Use(style: Style) -> None:
    """토큰을 갈아끼운다. 위젯을 짓기 전에 부른다."""
    global _CURRENT
    _CURRENT = style


def Mark(widget: QWidget, role: str) -> QWidget:
    """위젯에 역할을 표시하고 그대로 돌려준다.

    Args:
        widget: 표시할 위젯.
        role: 역할 이름.
    """
    widget.setProperty(ROLE, role)
    return widget


def Palette(style: Style | None = None) -> QPalette:
    """토큰 -> `QPalette`.

    Args:
        style: 쓸 토큰. 없으면 지금 것.
    """
    _t = (style or _CURRENT).tokens()
    _p = QPalette()
    for _role, _name in PALETTE.items():
        _p.setColor(getattr(QPalette, _role), QColor(_t[_name]))
    return _p


def Sheet(style: Style | None = None) -> str:
    """토큰 -> QSS. 자리에 걸면 그 안이 상속한다.

    Args:
        style: 쓸 토큰. 없으면 지금 것.
    """
    _t = (style or _CURRENT).tokens()
    return "\n".join(f'*[{ROLE}="{_role}"] {{ {_body.format(**_t)} }}'
                     for _role, _body in RULES.items())
