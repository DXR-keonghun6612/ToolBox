"""버튼 줄 - 선언한 버튼들을 한 줄로 놓고 눌린 버튼의 값을 냄.

버튼 하나는 부품 아님. 되풀이되는 것은 몇 개가 나란히 붙어 한 벌로 도는 것 - `▲▼✕` · `↶↷`.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from .....style import Now
from ...._item import Button

__all__ = ["Button_bar"]


class Button_bar(QWidget):
    """선언한 버튼들을 한 줄로.

    `value` 를 안 준 버튼은 자리 번호를 냄. `▲▼` 에 `-1`/`+1` 을 주면 받는 쪽이 옮길 칸 수로
    번역할 일이 없음.

    Attributes:
        fired: 눌린 버튼의 값.
    """

    fired = Signal(int)

    def __init__(self, buttons: list[Button],
                 parent: QWidget | None = None) -> None:
        """줄을 구성.

        Args:
            buttons: 버튼 선언. 순서가 곧 자리 번호.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        _size = Now()["button"]
        self._buttons: list[QToolButton] = []
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(0)          # 한 벌로 붙어 도는 버튼들
        for _at, _spec in enumerate(buttons):
            _b = QToolButton()
            _b.setText(_spec.text)
            _b.setToolTip(_spec.tip)
            _b.setFixedSize(_size, _size)
            _b.setEnabled(_spec.enabled)
            _value = _at if _spec.value is None else _spec.value
            _b.clicked.connect(lambda _c=False, _v=_value: self.fired.emit(_v))
            self._buttons.append(_b)
            _lay.addWidget(_b)

    def arm(self, at: int, on: bool) -> None:
        """`at` 버튼을 켜고 끔."""
        if 0 <= at < len(self._buttons):
            self._buttons[at].setEnabled(on)

    def arm_all(self, on: bool) -> None:
        """모든 버튼을 켜고 끔."""
        for _b in self._buttons:
            _b.setEnabled(on)
