"""읽기 전용 한 칸 - 라벨 + 보여 주기만 하는 값.

자료형을 안 가림. 값을 그대로 들고 보이기만 글자로 바꿈 - 왕복해도 자료형이 안 상함.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .....style import LABEL, READOUT, Mark, Now
from ...._value import Value


class Readout_row(Value):
    """값 하나를 보여 주기만 하는 행. 사람이 못 고치므로 `edited` 가 안 남.

    Attributes:
        value_changed: 계약을 채우는 자리. 안 남
    """

    value_changed = Signal(object)

    def __init__(self, label: str = "", default: Any = None, tooltip: str = "",
                 display: Callable[[Any], str] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        label: 왼쪽 라벨. 비면 라벨 없이 값만.
        default: 초기값.
        tooltip: 위젯 툴팁.
        display: 값 -> 보일 글자. 비면 목록은 쉼표로, 나머지는 `str`.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._value = default
        self._display = display

        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["gap"])
        if label:
            _lay.addWidget(Mark(QLabel(label), LABEL))

        self._read = Mark(QLabel(self._text(default)), READOUT)
        _lay.addWidget(self._read, stretch=1)

        if tooltip:
            self.setToolTip(tooltip)

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
        self._read.setText(self._text(value))
