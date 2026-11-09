"""수 한 칸 - 라벨 + 슬라이더 + 값 표시.

정수와 실수가 갈리는 것은 payload 자료형 하나. 스핀 대신 읽기 라벨을 쓰는 것, 기준값에
달라붙는 것, 폭을 좁히는 것은 모두 인자 - 표현마다 클래스를 안 세움.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

from .....style import LABEL, READOUT, VALUE, Mark, Now
from ...._value import Value


class _Slider(QSlider):
    """스냅 지점에 달라붙는 가로 슬라이더. `snaps` 가 비면 평범한 슬라이더.

    붙는 폭은 범위에 비례(3%) - 범위가 `-100~100` 이든 `0~1000` 이든 손끝 감각이 같게.

    Args:
        snaps: 달라붙을 값들. 범위 밖 값은 무시.
        parent: 부모 위젯.
    """

    _SNAP_RATIO = 0.03

    def __init__(self, snaps: list[int] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._snaps = list(snaps or [])
        self._snapping = False
        self.valueChanged.connect(self._snap)

    def _tolerance(self) -> int:
        return max(1, round((self.maximum() - self.minimum()) * self._SNAP_RATIO))

    def _snap(self, value: int) -> None:
        """스냅 지점 근처면 그 값으로 당김 (재진입 방지 - `setValue` 가 이 슬롯을 다시 부름)."""
        if self._snapping or not self._snaps:
            return
        _near = min(self._snaps, key=lambda _s: abs(_s - value))
        if _near != value and abs(_near - value) <= self._tolerance():
            self._snapping = True
            self.setValue(_near)
            self._snapping = False

    def paintEvent(self, event) -> None:
        """기본 슬라이더 위에 스냅 눈금. 어디에 붙는지 안 보이면 없는 것과 같음."""
        super().paintEvent(event)
        if not self._snaps:
            return
        _opt = QStyleOptionSlider()
        self.initStyleOption(_opt)
        _groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, _opt, QStyle.SubControl.SC_SliderGroove, self)
        _handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, _opt, QStyle.SubControl.SC_SliderHandle, self)
        _span = _groove.width() - _handle.width()

        _painter = QPainter(self)
        _painter.setPen(QPen(self.palette().mid().color(), 1))
        for _s in self._snaps:
            if not self.minimum() <= _s <= self.maximum():
                continue
            _x = _groove.left() + _handle.width() / 2 + QStyle.sliderPositionFromValue(
                self.minimum(), self.maximum(), _s, _span)
            _painter.drawLine(int(_x), _groove.top(), int(_x), _groove.top() + 3)


class Int_slider_row(Value):
    """정수 하나. 슬라이더와 값 표시가 맞물림.

    Attributes:
        value_changed: 새 정수
    """

    value_changed = Signal(int)

    def __init__(self, label: str, min_val: int, max_val: int, default: int,
                 snaps: list[int] | None = None, readout: bool = False,
                 tooltip: str = "", parent: QWidget | None = None) -> None:
        """Args:
        label: 왼쪽 라벨. 비면 라벨 없이 값만.
        min_val: 최솟값.
        max_val: 최댓값.
        default: 초기값.
        snaps: 달라붙을 값들 (밝기의 `[0]`, 배율의 `[0, 100, 200]`). 비면 안 달라붙음.
        readout: 스핀 대신 읽기 라벨. 툴바에 얹어 보면서 맞추는 값에 - 폭도 좁아짐.
        tooltip: 위젯 툴팁.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        _style = Now()
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(_style["gap"])
        if label:
            _lay.addWidget(Mark(QLabel(label), LABEL))

        self._slider = _Slider(snaps)
        self._slider.setRange(min_val, max_val)
        self._slider.setValue(default)
        if readout:
            self._slider.setFixedWidth(_style["compact_width"])
            _lay.addWidget(self._slider)
        else:
            _lay.addWidget(self._slider, stretch=1)

        self._read: QLabel | None = None
        self._spin: QSpinBox | None = None
        if readout:
            self._read = Mark(QLabel(str(default)), READOUT)
            _lay.addWidget(self._read)
        else:
            self._spin = QSpinBox()
            self._spin.setRange(min_val, max_val)
            self._spin.setValue(default)
            Mark(self._spin, VALUE)
            _lay.addWidget(self._spin)
            self._spin.valueChanged.connect(self._slider.setValue)

        if tooltip:
            self.setToolTip(tooltip)
        self._slider.valueChanged.connect(self._on_changed)

    def _on_changed(self, v: int) -> None:
        """사람이 고쳤을 때의 후처리."""
        self._show(v)
        self.value_changed.emit(v)
        self.edited.emit()

    def _show(self, v: int) -> None:
        """값 표시를 맞춤. 스핀이면 되울림을 막고."""
        if self._read is not None:
            self._read.setText(str(v))
            return
        self._spin.blockSignals(True)
        self._spin.setValue(v)
        self._spin.blockSignals(False)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value) -> None:
        """스냅 안 걺 - 준 값이 조용히 바뀌면 안 됨. 스냅은 드래그에만."""
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        self._show(self._slider.value())   # 범위 자름까지 반영


class Float_slider_row(Value):
    """실수 하나. 슬라이더 한 칸을 `step` 으로 잘라 씀.

    Attributes:
        value_changed: 새 실수
    """

    value_changed = Signal(float)

    def __init__(self, label: str, min_val: float, max_val: float, default: float,
                 step: float = 0.05, decimals: int = 2, tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        label: 왼쪽 라벨. 비면 라벨 없이 값만.
        min_val: 최솟값.
        max_val: 최댓값.
        default: 초기값.
        step: 슬라이더 한 칸 · 스핀 증감 단위.
        decimals: 스핀 소수 자릿수.
        tooltip: 위젯 툴팁.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._min = min_val
        self._step = step
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["gap"])
        if label:
            _lay.addWidget(Mark(QLabel(label), LABEL))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, round((max_val - min_val) / step))
        self._slider.setValue(self._index(default))
        _lay.addWidget(self._slider, stretch=1)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(min_val, max_val)
        self._spin.setSingleStep(step)
        self._spin.setDecimals(decimals)
        self._spin.setValue(default)
        Mark(self._spin, VALUE)
        _lay.addWidget(self._spin)

        if tooltip:
            self.setToolTip(tooltip)
        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)

    def _index(self, v: float) -> int:
        """실수 -> 슬라이더 칸."""
        return round((float(v) - self._min) / self._step)

    def _on_slider(self, idx: int) -> None:
        """슬라이더를 끌었을 때 - 스핀을 맞추고 신호."""
        _v = round(self._min + idx * self._step, 8)
        self._spin.blockSignals(True)
        self._spin.setValue(_v)
        self._spin.blockSignals(False)
        self._emit(_v)

    def _on_spin(self, v: float) -> None:
        """스핀을 고쳤을 때 - 슬라이더를 맞추고 신호."""
        self._slider.blockSignals(True)
        self._slider.setValue(self._index(v))
        self._slider.blockSignals(False)
        self._emit(v)

    def _emit(self, v: float) -> None:
        """사람이 고쳤을 때의 후처리."""
        self.value_changed.emit(v)
        self.edited.emit()

    def value(self) -> float:
        return self._spin.value()

    def set_value(self, value) -> None:
        """슬라이더 · 스핀을 함께 맞춤."""
        self._spin.blockSignals(True)
        self._slider.blockSignals(True)
        self._spin.setValue(float(value))
        self._slider.setValue(self._index(value))
        self._spin.blockSignals(False)
        self._slider.blockSignals(False)
