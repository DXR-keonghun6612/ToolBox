"""수 control - 스핀은 늘, 슬라이더는 필요할 때 더함.

빈 값 - `empty` 에 글자를 주면 켜짐. 하한 한 칸 아래가 빈 값 자리, 스핀은 그 글자를 보임.
글자를 다 지워도 빈 값.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen, QValidator
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

__all__ = ["Float_slider", "Float_spin", "Int_slider", "Int_spin"]

#: 빈 값일 때 슬라이더에 거는 Qt 속성. style selector `QSlider[empty="true"]` 가 흐리게.
EMPTY = "empty"


# ── 스핀 ──────────────────────────────────────────────────────────────────────
def _range(spin: QAbstractSpinBox, min: float, max: float, step: float,
           empty: str | None) -> None:
    """범위 · 단위 · 빈 값 자리를 걺.

    Raises:
        ValueError: `empty` 가 빈 글자일 때 - Qt 가 빈 글자를 끔으로 읽어 빈 값 자리가 숫자로 보임.
    """
    if empty is not None and not empty:
        raise ValueError("empty must be non-empty text - an empty string shows the sentinel as a number")
    spin.setRange(min if empty is None else min - step, max)
    spin.setSingleStep(step)
    if empty is not None:
        spin.setSpecialValueText(empty)


def _read(spin: QAbstractSpinBox, raw: float, empty: str | None) -> Any:
    """Qt 값 -> control 값. 빈 값 자리면 None."""
    return None if empty is not None and raw == spin.minimum() else raw


def _write(spin: QAbstractSpinBox, value: Any, empty: str | None, cast: type) -> None:
    """control 값 -> Qt 값. 신호 안 냄.

    Raises:
        ValueError: 빈 값이 꺼진 control 에 None 일 때.
    """
    if value is None and empty is None:
        raise ValueError(f"{type(spin).__name__}: None needs `empty` set")
    spin.blockSignals(True)
    spin.setValue(spin.minimum() if value is None else cast(value))
    spin.blockSignals(False)


def _blank(text: str, empty: str | None) -> bool:
    """사람이 글자를 다 지웠나 - 빈 값이 켜진 때만."""
    return empty is not None and not text.strip()


class Int_spin(QSpinBox):
    """정수 하나 - 스핀.

    Attributes:
        value_changed: 새 정수 또는 None
    """

    value_changed = Signal(object)

    def __init__(self, min: int, max: int, default: int | None, step: int = 1,
                 empty: str | None = None, parent: QWidget | None = None) -> None:
        """Args:
        min: 하한.
        max: 상한.
        default: 초기값. None 이면 빈 값 - `empty` 가 있어야 함.
        step: 증감 단위.
        empty: 빈 값일 때 보일 글자. None 이면 빈 값 꺼짐.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._empty = empty
        _range(self, min, max, step, empty)
        self.set_value(default)
        self.valueChanged.connect(self._on_changed)

    def _on_changed(self, _raw: int) -> None:
        self.value_changed.emit(self.value())

    def validate(self, text: str, pos: int):
        if _blank(text, self._empty):
            return QValidator.State.Acceptable
        return super().validate(text, pos)

    def valueFromText(self, text: str) -> int:
        return self.minimum() if _blank(text, self._empty) else super().valueFromText(text)

    def value(self) -> int | None:
        return _read(self, QSpinBox.value(self), self._empty)

    def set_value(self, value) -> None:
        _write(self, value, self._empty, int)


class Float_spin(QDoubleSpinBox):
    """실수 하나 - 스핀.

    Attributes:
        value_changed: 새 실수 또는 None
    """

    value_changed = Signal(object)

    def __init__(self, min: float, max: float, default: float | None, step: float = 0.05,
                 decimals: int = 2, empty: str | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        min: 하한.
        max: 상한.
        default: 초기값. None 이면 빈 값 - `empty` 가 있어야 함.
        step: 증감 단위.
        decimals: 소수 자릿수. 모자라면 스핀이 값을 그 자리로 반올림해 듦.
        empty: 빈 값일 때 보일 글자. None 이면 빈 값 꺼짐.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._empty = empty
        self.setDecimals(decimals)      # 범위보다 먼저 - 범위가 이 자릿수로 반올림됨
        _range(self, min, max, step, empty)
        self.set_value(default)
        self.valueChanged.connect(self._on_changed)

    def _on_changed(self, _raw: float) -> None:
        self.value_changed.emit(self.value())

    def validate(self, text: str, pos: int):
        if _blank(text, self._empty):
            return QValidator.State.Acceptable
        return super().validate(text, pos)

    def valueFromText(self, text: str) -> float:
        return self.minimum() if _blank(text, self._empty) else super().valueFromText(text)

    def value(self) -> float | None:
        return _read(self, QDoubleSpinBox.value(self), self._empty)

    def set_value(self, value) -> None:
        _write(self, value, self._empty, float)


# ── 슬라이더를 더한 꼴 ────────────────────────────────────────────────────────
class _Snap_slider(QSlider):
    """스냅 지점에 달라붙는 가로 슬라이더. `snaps` 가 비면 평범한 슬라이더.

    붙는 폭은 범위에 비례(3 %) - 범위가 `-100 ~ 100` 이든 `0 ~ 1000` 이든 손끝 감각이 같게.
    """

    _SNAP_RATIO = 0.03

    def __init__(self, snaps: list[int] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        snaps: 달라붙을 슬라이더 자리들. 범위 밖 값은 무시.
        parent: 부모 위젯.
        """
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._snaps = list(snaps or [])
        self._snapping = False
        self.valueChanged.connect(self._snap)

    def _tolerance(self) -> int:
        return max(1, round((self.maximum() - self.minimum()) * self._SNAP_RATIO))

    def _snap(self, value: int) -> None:
        # setValue 가 이 슬롯을 다시 부름 - 재진입 막음
        if self._snapping or not self._snaps:
            return
        _near = min(self._snaps, key=lambda _s: abs(_s - value))
        if _near != value and abs(_near - value) <= self._tolerance():
            self._snapping = True
            self.setValue(_near)
            self._snapping = False

    def paintEvent(self, event) -> None:
        """기본 슬라이더 위에 스냅 눈금."""
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


class _Slider_spin(QWidget):
    """스핀 하나 + 슬라이더. 값은 스핀이 듦, 슬라이더는 그 값을 따라감.

    빈 값이면 슬라이더는 하한에서 `empty` 속성이 켜짐. 누르거나 끌면 값이 생김.
    슬라이더 자리 <-> 값 변환은 서브클래스.

    Attributes:
        value_changed: 새 값 또는 None
    """

    value_changed = Signal(object)

    def __init__(self, spin: Int_spin | Float_spin, positions: int,
                 snaps: list[int] | None, parent: QWidget | None) -> None:
        """Args:
        spin: 값을 드는 스핀.
        positions: 슬라이더 칸 수 - 자리는 `0 ~ positions`.
        snaps: 달라붙을 슬라이더 자리들.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)

        self._spin = spin
        self._slider = _Snap_slider(snaps)
        self._slider.setRange(0, positions)
        _lay.addWidget(self._slider, stretch=1)
        _lay.addWidget(self._spin)
        self._follow()

        self._spin.value_changed.connect(self._on_spin)
        self._slider.valueChanged.connect(self._on_slider)
        self._slider.sliderPressed.connect(self._on_pressed)

    def _position(self, value: Any) -> int:
        """값 -> 슬라이더 자리."""
        raise NotImplementedError(f"{type(self).__name__}._position")

    def _value_at(self, position: int) -> Any:
        """슬라이더 자리 -> 값."""
        raise NotImplementedError(f"{type(self).__name__}._value_at")

    def _follow(self) -> None:
        """슬라이더를 스핀 값에 맞춤. 신호 안 냄."""
        _v = self._spin.value()
        self._slider.blockSignals(True)
        self._slider.setValue(0 if _v is None else self._position(_v))
        self._slider.blockSignals(False)
        self._slider.setProperty(EMPTY, _v is None)
        self._slider.style().polish(self._slider)

    def _on_spin(self, _value: Any) -> None:
        self._follow()
        self._emit()

    def _on_slider(self, position: int) -> None:
        # 스냅이 이 신호 안에서 자리를 옮김 - 지난 자리로 온 바깥 호출은 버림
        if position != self._slider.value():
            return
        self._spin.set_value(self._value_at(position))
        self._follow()
        self._emit()

    def _on_pressed(self) -> None:
        # 빈 값에서 하한 자리를 누르면 valueChanged 가 안 남 - 그 자리 값으로 채움
        if self._spin.value() is None:
            self._on_slider(self._slider.value())

    def _emit(self) -> None:
        self.value_changed.emit(self.value())

    def value(self) -> Any:
        return self._spin.value()

    def set_value(self, value) -> None:
        self._spin.set_value(value)
        self._follow()


class Int_slider(_Slider_spin):
    """정수 하나 - 슬라이더 + 스핀."""

    def __init__(self, min: int, max: int, default: int | None, step: int = 1,
                 snaps: list[int] | None = None, empty: str | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        min: 하한.
        max: 상한.
        default: 초기값. None 이면 빈 값 - `empty` 가 있어야 함.
        step: 슬라이더 한 칸 · 스핀 증감 단위.
        snaps: 달라붙을 값들. 비면 안 달라붙음.
        empty: 빈 값일 때 보일 글자. None 이면 빈 값 꺼짐.
        parent: 부모 위젯.
        """
        self._min = min
        self._step = step
        super().__init__(Int_spin(min, max, default, step, empty),
                         (max - min) // step,
                         [(_s - min) // step for _s in snaps or []], parent)

    def _position(self, value: int) -> int:
        return (value - self._min) // self._step

    def _value_at(self, position: int) -> int:
        return self._min + position * self._step


class Float_slider(_Slider_spin):
    """실수 하나 - 슬라이더 한 칸을 `step` 으로 잘라 씀 + 스핀."""

    def __init__(self, min: float, max: float, default: float | None, step: float = 0.05,
                 decimals: int = 2, empty: str | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        min: 하한.
        max: 상한.
        default: 초기값. None 이면 빈 값 - `empty` 가 있어야 함.
        step: 슬라이더 한 칸 · 스핀 증감 단위.
        decimals: 소수 자릿수. 모자라면 스핀이 값을 그 자리로 반올림해 듦.
        empty: 빈 값일 때 보일 글자. None 이면 빈 값 꺼짐.
        parent: 부모 위젯.
        """
        self._min = min
        self._step = step
        super().__init__(Float_spin(min, max, default, step, decimals, empty),
                         round((max - min) / step), None, parent)

    def _position(self, value: float) -> int:
        return round((float(value) - self._min) / self._step)

    def _value_at(self, position: int) -> float:
        return round(self._min + position * self._step, 8)
