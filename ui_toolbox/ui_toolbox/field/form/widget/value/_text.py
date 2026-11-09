"""글자 한 칸 - 라벨 + 한 줄 입력.

목록도 같은 골격. 담는 자료형만 갈려 `value` · `set_value` 에서 쉼표로 가름.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from .....style import LABEL, Mark
from ...._value import Value


class Text_row(Value):
    """글자 하나를 받는 행.

    Attributes:
        value_changed: 새 글자
    """

    value_changed = Signal(str)

    def __init__(self, label: str = "", default=None, tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        label: 왼쪽 라벨. 비면 라벨 없이 값만.
        default: 초기값.
        tooltip: 위젯 툴팁.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        if label:
            _lay.addWidget(Mark(QLabel(label), LABEL))

        self._edit = QLineEdit(self._text(default))
        _lay.addWidget(self._edit, stretch=1)

        if tooltip:
            self.setToolTip(tooltip)
        self._edit.textChanged.connect(self._on_changed)

    @staticmethod
    def _text(value) -> str:
        """값 -> 칸에 적을 글자."""
        return "" if value is None else str(value)

    def _on_changed(self, _text: str) -> None:
        """사람이 고쳤을 때의 후처리. payload 는 `value` 가 정함."""
        self.value_changed.emit(self.value())
        self.edited.emit()

    def value(self) -> str:
        return self._edit.text()

    def set_value(self, value) -> None:
        self._edit.blockSignals(True)
        self._edit.setText(self._text(value))
        self._edit.blockSignals(False)


class List_row(Text_row):
    """쉼표로 가른 글자 목록을 받는 행.

    Attributes:
        value_changed: 새 목록
    """

    value_changed = Signal(list)

    @staticmethod
    def _text(value) -> str:
        return ", ".join(value) if value else ""

    def value(self) -> list[str]:
        return [_s.strip() for _s in self._edit.text().split(",") if _s.strip()]
