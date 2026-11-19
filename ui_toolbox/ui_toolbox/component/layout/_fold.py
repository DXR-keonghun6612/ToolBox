"""fold - 자식마다 머리 + 접히는 본문. 세로로 쌓음.

- 머리 글자는 자식의 `title`
- 접으면 그 구역의 최대 높이를 머리 높이로 못박음 - 형제가 자리를 가져감. 펴면 풂
- 구역 사이는 splitter 막대 - 사람이 높이를 나눔
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QSplitter, QToolButton, QVBoxLayout, QWidget

__all__ = ["Fold"]

#: Qt 의 `QWIDGETSIZE_MAX` - `제한 없음` 파수값. PySide6 빌드에 따라 심볼이 없어 값으로 둠.
_MAX_H = 16_777_215


class _Section(QWidget):
    """구역 하나 - 머리 버튼 + 본문.

    Attributes:
        toggled: 펼침 참, 접힘 거짓
    """

    toggled = Signal(bool)

    def __init__(self, title: str, content: QWidget) -> None:
        super().__init__()
        self._content = content
        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(0)
        self.head = QToolButton()
        self.head.setText(title)
        self.head.setCheckable(True)
        self.head.setChecked(True)
        self.head.setAutoRaise(True)
        self.head.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.head.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.head.toggled.connect(self._apply)
        _lay.addWidget(self.head)
        _lay.addWidget(content, stretch=1)
        self._apply(True)

    def _apply(self, expanded: bool) -> None:
        self.head.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._content.setVisible(expanded)
        self.setMaximumHeight(_MAX_H if expanded else self.head.sizeHint().height())
        self.toggled.emit(expanded)


class Fold(QSplitter):
    """구역을 세로로 쌓는 위젯."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setChildrenCollapsible(False)

    def add(self, child: QWidget, title: str) -> None:
        """구역 하나를 끝에 붙임. 펼친 채로."""
        self.addWidget(_Section(title, child))

    def set_expanded(self, at: int, expanded: bool) -> None:
        """`at` 번째 구역을 펴거나 접음. 머리 상태를 바꾸므로 `toggled` 가 남.

        Raises:
            IndexError: 구역 밖 번호일 때.
        """
        if not 0 <= at < self.count():
            raise IndexError(f"section {at} out of range - {self.count()} sections")
        self.widget(at).head.setChecked(expanded)

    def is_expanded(self, at: int) -> bool:
        """`at` 번째 구역이 펴져 있나.

        Raises:
            IndexError: 구역 밖 번호일 때.
        """
        if not 0 <= at < self.count():
            raise IndexError(f"section {at} out of range - {self.count()} sections")
        return self.widget(at).head.isChecked()
