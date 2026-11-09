"""접히는 섹션 - 머리를 누르면 본문이 숨음.

주제를 안 듦. 무엇이 본문인지 안 물으므로 어느 주제에도 붙음 - `style` 하나만 봄.

접힐 때 최대 높이를 머리 높이로 못박음. `QSplitter` 안에서 `setVisible` 만 하면 splitter 가
자리를 계속 물고 있어 접은 값이 안 남. 펴면 풀어 다시 끌 수 있게.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QToolButton, QVBoxLayout, QWidget

from .style import SECTION, Mark

__all__ = ["Collapsible"]

_MAX_H = 16_777_215        # Qt 의 QWIDGETSIZE_MAX. PySide6 빌드에 따라 심볼이 없어 값으로 둠


class Collapsible(QWidget):
    """제목 머리 + 접히는 본문. 접으면 머리만 남고 형제가 공간을 가져감.

    Attributes:
        toggled: 펼침 · 접힘이 바뀜
    """

    toggled = Signal(bool)

    def __init__(self, title: str, content: QWidget, *,
                 expanded: bool = True, parent=None) -> None:
        """Args:
        title: 머리에 적을 문구.
        content: 접힐 본문 위젯.
        expanded: 처음에 펴져 있나.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._content = content

        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(0)

        self._header = QToolButton()
        self._header.setText(title)
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.setAutoRaise(True)
        self._header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        Mark(self._header, SECTION)
        self._header.toggled.connect(self._apply)

        _lay.addWidget(self._header)
        _lay.addWidget(content, stretch=1)
        self._apply(expanded)

    def _apply(self, expanded: bool) -> None:
        """펼침 상태를 화살표 · 본문 · 최대 높이에 반영."""
        self._header.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._content.setVisible(expanded)
        self.setMaximumHeight(
            _MAX_H if expanded else self._header.sizeHint().height())
        self.toggled.emit(expanded)

    def set_expanded(self, expanded: bool) -> None:
        """코드가 펼치고 접음. 머리 상태를 바꾸므로 `toggled` 가 남."""
        self._header.setChecked(expanded)
