"""값 하나를 받는 위젯의 계약."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

__all__ = ["Value"]


class Value(QWidget):
    """폼이 보는 표면. payload 자료형을 안 물음.

    자료형 있는 `value_changed(T)` 는 직접 소비처용으로 각 위젯 소유.

    Attributes:
        edited: 사람이 고침. payload 없음 - `set_value` 로는 안 남
    """

    edited = Signal()

    def value(self) -> Any:
        """지금 값."""
        raise NotImplementedError(f"{type(self).__name__}.value")

    def set_value(self, value: Any) -> None:
        """값을 할당. 신호 안 냄 - 복원과 사람의 편집을 가름."""
        raise NotImplementedError(f"{type(self).__name__}.set_value")
