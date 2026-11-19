"""도구 선언 - 편집기가 할 수 있는 것을 데이터로 적음.

툴바 버튼, 단축키, 배타 묶음은 이 선언을 읽어서 지음 - 도구를 하나 더하면 셋이 함께 따라옴.
`group` 이 배타 축. 축이 몇 개인지는 편집기마다 다름.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Tool"]


@dataclass(frozen=True)
class Tool:
    """도구 하나.

    Attributes:
        key: 식별자 (`brush`, `box` 등).
        group: 배타 묶음 - 같은 묶음에서는 한 번에 하나만 고름.
        icon: 툴바 버튼에 보일 글자.
        label: 사람이 읽는 이름 - 툴팁 제목.
        shortcut: 단축키 (`B` 등). 없으면 빈 글자.
        tip: 툴팁 본문 - 이 도구가 하는 일.
    """

    key:      str
    group:    str
    icon:     str
    label:    str
    shortcut: str = ""
    tip:      str = ""

    def tooltip(self) -> str:
        """툴바 버튼의 툴팁 - 단축키를 함께."""
        _body = f"{self.label} - {self.tip}" if self.tip else self.label
        return f"{_body}  [{self.shortcut}]" if self.shortcut else _body
