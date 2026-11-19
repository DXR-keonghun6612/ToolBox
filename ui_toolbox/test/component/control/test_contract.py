"""control 계약 - 열두 control 모두 같은 흐름.

계약 : `value()`, `set_value()` 는 신호 없음, 사람이 고치면 `value_changed(값)` 한 번. 공통 base 없음 - 이름 규약.
readout 은 사람이 못 고치므로 `value_changed` 가 안 남.
"""

from __future__ import annotations

from unittest import mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from PySide6.QtTest import QTest

from ui_toolbox.component.control._bool import Bool_check, Bool_toggle
from ui_toolbox.component.control._choice import Choice_combo, Choice_radio, Choices_check
from ui_toolbox.component.control._number import Float_slider, Float_spin, Int_slider, Int_spin
from ui_toolbox.component.control._readout import Readout
from ui_toolbox.component.control._text import List_text, Path_text, Paths_text, Str_text


def _human(control, act, want, name: str) -> None:
    """사람의 조작 `act` 뒤 `value_changed` 한 번, 값 `want`. 이어서 `set_value` 는 신호 없이 값만."""
    _got: list = []
    control.value_changed.connect(_got.append)
    act(control)
    assert _got == [want], f"{name}: human edit -> value_changed {_got}"
    assert control.value() == want, f"{name} : value() {control.value()!r}"
    _got.clear()
    control.set_value(want)
    assert _got == [], f"{name}: set_value is silent"
    assert control.value() == want, f"{name}: value() after set_value"


def test_contract_flow():
    # 단계 : 계약 이름 - 열두 control 모두 가짐
    _all = [Bool_check(), Bool_toggle("t"), Int_spin(0, 10, 3), Float_spin(0, 1, 0.5), Int_slider(0, 100, 10),
            Float_slider(0, 1, 0.5), Str_text("a"), List_text(["a"]), Path_text(), Paths_text(),
            Choice_combo([1, 2], default=1), Choice_radio(["x", "y"], default="x"), Choices_check(["x", "y"])]
    for _c in _all:
        for _name in ("value", "set_value", "value_changed"):
            assert hasattr(_c, _name), f"contract: {type(_c).__name__} has no {_name}"

    # 단계 : bool
    _human(Bool_check(), lambda c: c.click(), True, "Bool_check")
    _human(Bool_toggle("t"), lambda c: c.click(), True, "Bool_toggle")

    # 단계 : 수
    _human(Int_spin(0, 10, 3), lambda c: c.stepBy(1), 4, "Int_spin")
    _human(Float_spin(0, 1, 0.5, step=0.1), lambda c: c.stepBy(1), 0.6, "Float_spin")
    _human(Int_slider(0, 100, 10, step=5), lambda c: c._slider.setValue(4), 20, "Int_slider")
    _human(Float_slider(0, 1, 0.5, step=0.1), lambda c: c._spin.stepBy(1), 0.6, "Float_slider")

    # 단계 : 글자
    _human(Str_text("a"), lambda c: (QTest.keyClicks(c, "b"), QTest.keyClick(c, Qt.Key.Key_Return)), "ab", "Str_text")
    _human(List_text(None), lambda c: (QTest.keyClicks(c, "a, b"), QTest.keyClick(c, Qt.Key.Key_Return)),
           ["a", "b"], "List_text")
    with mock.patch.object(QFileDialog, "getExistingDirectory", return_value="/etc"):
        _human(Path_text(), lambda c: c._browse(), "/etc", "Path_text")
    with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(["/a/1.png", "/a/2.png"], "")):
        _human(Paths_text(), lambda c: c._browse(), ["/a/1.png", "/a/2.png"], "Paths_text")

    # 단계 : 고르기
    _human(Choice_combo([1, 2, 3], default=1), lambda c: c.setCurrentIndex(2), 3, "Choice_combo")
    _human(Choice_radio(["x", "y"], default="x"), lambda c: c._group.button(1).click(), "y", "Choice_radio")
    _human(Choices_check(["x", "y", "z"]), lambda c: c._group.button(2).click(), ["z"], "Choices_check")

    # 단계 : readout - 신호 없음, 값은 그대로 오감
    _r = Readout([1, 2])
    _got: list = []
    _r.value_changed.connect(_got.append)
    _r.set_value({"k": 1})
    assert _got == [] and _r.value() == {"k": 1}, "Readout: value kept, silent"
    assert Readout([1, 2]).text() == "1, 2" and Readout(None).text() == "", "Readout: list joined by comma, None empty"
    assert Readout(3, display=lambda v: f"<{v}>").text() == "<3>", "Readout : display"
