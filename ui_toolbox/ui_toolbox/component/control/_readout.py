"""읽기 전용 control - 아무 자료형의 readout.

값을 그대로 들고 보이기만 글자로 - 왕복해도 자료형이 안 상함.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QWidget

__all__ = ["Readout"]


class Readout(QLabel):
    """값 하나를 보여 주기만. 사람이 못 고치므로 `value_changed` 가 안 남.

    Attributes:
        value_changed: 계약을 채우는 자리. 안 남
    """

    value_changed = Signal(object)

    def __init__(self, default: Any = None,
                 display: Callable[[Any], str] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        default: 초기값.
        display: 값 -> 보일 글자. 비면 목록은 쉼표로, 나머지는 `str`. None 은 늘 빈 글자.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._display = display
        self.set_value(default)

    def _text(self, value: Any) -> str:
        """값 -> 보일 글자."""
        if value is None:
            return ""
        if self._display is not None:
            return self._display(value)
        if isinstance(value, (list, tuple)):
            return ", ".join(str(_v) for _v in value)
        return str(value)

    def value(self) -> Any:
        return self._value

    def set_value(self, value) -> None:
        self._value = value
        self.setText(self._text(value))
