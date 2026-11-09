"""참 · 거짓 한 칸 - 라벨 붙은 체크박스."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from ...._value import Value


class Check_row(Value):
    """체크박스 하나로 참 · 거짓을 받는 행.

    Attributes:
        value_changed: 새 참 · 거짓
    """

    value_changed = Signal(bool)

    def __init__(self, label: str = "", default: bool = False, tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        label: 체크박스 옆 문구. 비면 상자만.
        default: 초기값.
        tooltip: 위젯 툴팁.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)

        self._box = QCheckBox(label)
        self._box.setChecked(bool(default))
        _lay.addWidget(self._box)

        if tooltip:
            self.setToolTip(tooltip)
        self._box.toggled.connect(self._on_changed)

    def _on_changed(self, v: bool) -> None:
        """사람이 고쳤을 때의 후처리."""
        self.value_changed.emit(v)
        self.edited.emit()

    def value(self) -> bool:
        return self._box.isChecked()

    def set_value(self, value) -> None:
        self._box.blockSignals(True)
        self._box.setChecked(bool(value))
        self._box.blockSignals(False)
