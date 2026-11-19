"""bool control - check, toggle."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QPushButton, QWidget

__all__ = ["Bool_check", "Bool_toggle"]


class Bool_check(QCheckBox):
    """체크박스.

    Attributes:
        value_changed: 새 참 · 거짓
    """

    value_changed = Signal(bool)

    def __init__(self, default: bool = False, text: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        default: 초기값.
        text: 상자 옆 문구. 비면 상자만.
        parent: 부모 위젯.
        """
        super().__init__(text, parent)
        self.set_value(default)
        self.toggled.connect(self._on_changed)

    def _on_changed(self, v: bool) -> None:
        self.value_changed.emit(v)

    def value(self) -> bool:
        return self.isChecked()

    def set_value(self, value) -> None:
        self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(False)


class Bool_toggle(QPushButton):
    """눌린 채로 남는 버튼.

    Attributes:
        value_changed: 새 참 · 거짓
    """

    value_changed = Signal(bool)

    def __init__(self, text: str, default: bool = False,
                 parent: QWidget | None = None) -> None:
        """Args:
        text: 버튼 글자.
        default: 초기값.
        parent: 부모 위젯.
        """
        super().__init__(text, parent)
        self.setCheckable(True)
        self.set_value(default)
        self.toggled.connect(self._on_changed)

    def _on_changed(self, v: bool) -> None:
        self.value_changed.emit(v)

    def value(self) -> bool:
        return self.isChecked()

    def set_value(self, value) -> None:
        self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(False)
