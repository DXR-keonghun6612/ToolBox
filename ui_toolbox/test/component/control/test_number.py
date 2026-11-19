"""수 control - 빈 값, 슬라이더 따라감, 스냅 흐름.

빈 값 : `empty` 글자를 줄 때만 켜짐. 하한 한 칸 아래가 빈 값 자리, 스핀은 그 글자를 보임. 글자를 다 지워도 빈 값.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ui_toolbox.component.control._number import Float_slider, Float_spin, Int_slider, Int_spin


def test_number_flow():
    # 단계 : 빈 값 꺼짐 - None 은 실패
    _plain = Int_spin(0, 10, 3)
    assert _plain.minimum() == 0, "empty off: minimum unchanged"
    with pytest.raises(ValueError):
        _plain.set_value(None)
    with pytest.raises(ValueError):
        Int_spin(0, 10, None)

    # 실패 갈래 : 빈 글자 empty - Qt 가 끔으로 읽음
    with pytest.raises(ValueError):
        Int_spin(0, 10, 3, empty="")

    # 단계 : 빈 값 켜짐 - 하한 한 칸 아래, 그 글자를 보임
    _f = Float_spin(0.0, 1.0, None, step=0.1, empty="auto")
    assert _f.value() is None and _f.text() == "auto", "empty: starts None, text shown"
    assert _f.minimum() == pytest.approx(-0.1), "empty: sentinel one step below minimum"
    _f.set_value(0.4)
    assert _f.value() == pytest.approx(0.4), "empty: set value"
    _f.set_value(None)
    assert _f.value() is None, "empty: set None"

    # 단계 : 글자를 다 지우면 빈 값
    _i = Int_spin(0, 10, 5, empty="auto")
    _i.show()
    _got: list = []
    _i.value_changed.connect(_got.append)
    _le = _i.lineEdit()
    _le.selectAll()
    QTest.keyClick(_le, Qt.Key.Key_Delete)
    QTest.keyClick(_le, Qt.Key.Key_Return)
    assert _i.value() is None and _got and _got[-1] is None, "clear: empty, value_changed(None)"

    # 단계 : 슬라이더 - 스핀을 따라감, 빈 값이면 하한에서 empty 속성
    _s = Float_slider(0.0, 1.0, 0.5, step=0.1, empty="auto")
    assert _s._slider.value() == 5, "slider: initial position"
    _s.set_value(None)
    assert _s.value() is None and _s._slider.value() == 0, "slider: empty at minimum"
    assert _s._slider.property("empty") is True, "slider: empty property"
    _s.set_value(0.8)
    assert _s._slider.value() == 8 and _s._slider.property("empty") is False, "slider: follows a value"

    # 단계 : 빈 슬라이더를 누르면 그 자리 값이 생김
    _s.set_value(None)
    _got = []
    _s.value_changed.connect(_got.append)
    _s._slider.sliderPressed.emit()
    assert _s.value() == pytest.approx(0.0) and _got, "slider: press on empty gives minimum"

    # 단계 : 스냅 - 한 번만 내고 스냅한 값
    _n = Int_slider(0, 100, 10, step=5, snaps=[50])
    _got = []
    _n.value_changed.connect(_got.append)
    _n._slider.setValue(9)
    assert _got == [50] and _n.value() == 50, f"snap: {_got}"
