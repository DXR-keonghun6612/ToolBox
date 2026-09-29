"""켜고 끄는 실수 한 칸 - 체크박스 + 슬라이더. 끄면 `None`.

`없음` 과 `0` 이 다른 값이라 슬라이더 하나로는 못 실음.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from .....style import Now
from ...._value import Value
from ._number import Float_slider_row


class Optional_float_row(Value):
    """체크박스로 켠 뒤 슬라이더로 고르는 행. 꺼져 있으면 값이 `None`.

    Attributes:
        value_changed: 새 `float` 또는 `None`
    """

    value_changed = Signal(object)

    def __init__(self, label: str = "", min_val: float = 0.0, max_val: float = 1.0,
                 default=None, step: float = 0.05, decimals: int = 2, tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        label: 체크박스에 붙일 문구. 슬라이더는 그 아래 들여씀. 비면 둘 다 없이.
        min_val: 최솟값.
        max_val: 최댓값.
        default: 초기값. `None` 이면 꺼진 채로 서고 슬라이더는 범위 한가운데.
        step: 슬라이더 한 칸.
        decimals: 스핀 소수 자릿수.
        tooltip: 위젯 툴팁.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["tight"])

        self._box = QCheckBox(label)
        self._box.setChecked(default is not None)
        _lay.addWidget(self._box)

        self._slider = Float_slider_row(
            f"  -> {label}" if label else "", min_val, max_val,
            float(default) if default is not None else (min_val + max_val) / 2,
            step=step, decimals=decimals, tooltip=tooltip)
        self._slider.setEnabled(default is not None)
        _lay.addWidget(self._slider)

        if tooltip:
            self.setToolTip(tooltip)
        self._box.toggled.connect(self._slider.setEnabled)
        self._box.toggled.connect(self._on_changed)
        self._slider.edited.connect(self._on_changed)

    def _on_changed(self, *_) -> None:
        """사람이 고쳤을 때의 후처리. 체크박스와 슬라이더가 같은 값 하나를 냄."""
        self.value_changed.emit(self.value())
        self.edited.emit()

    def value(self) -> float | None:
        return self._slider.value() if self._box.isChecked() else None

    def set_value(self, value) -> None:
        self._box.blockSignals(True)
        self._box.setChecked(value is not None)
        self._box.blockSignals(False)
        self._slider.setEnabled(value is not None)
        if value is not None:
            self._slider.set_value(float(value))
