"""계약 - `value` · `set_value` · `edited` 세 표면.

`set_value` 가 신호를 내면 복원이 사람의 편집으로 읽힘. 그 누출을 여기서 막음.
"""

from __future__ import annotations

import pytest

from ui_toolbox.field._value import Value
from ui_toolbox.field.form.widget import (
    Check_row,
    Float_slider_row,
    Int_slider_row,
    List_row,
    Optional_float_row,
    Path_row,
    Text_row,
)


def _int_row() -> Int_slider_row:
    return Int_slider_row("i", 0, 10, 3)


def _float_row() -> Float_slider_row:
    return Float_slider_row("f", 0.0, 1.0, 0.5, step=0.1)


def _snap_row() -> Int_slider_row:
    return Int_slider_row("s", -100, 100, 0, snaps=[0], readout=True)


def _check_row() -> Check_row:
    return Check_row("c", False)


def _text_row() -> Text_row:
    return Text_row("t", "처음")


def _list_row() -> List_row:
    return List_row("l", ["a", "b"])


def _optional_row() -> Optional_float_row:
    return Optional_float_row("o", 0.0, 1.0, None, step=0.1)


def _path_row() -> Path_row:
    return Path_row("p", refresh=True)


def _log(widget: Value) -> tuple[list, list]:
    """`edited` 와 `value_changed` 를 각각 담을 자리."""
    _edited: list = []
    _typed: list = []
    widget.edited.connect(lambda: _edited.append(True))
    widget.value_changed.connect(_typed.append)
    return _edited, _typed


_MAKE = [_int_row, _float_row, _snap_row, _check_row, _text_row, _list_row,
         _optional_row, _path_row]


@pytest.mark.parametrize("make", _MAKE)
def test_value_widgets_inherit_contract(make):
    assert isinstance(make(), Value)


@pytest.mark.parametrize("make, given", [
    (_int_row, 7),
    (_float_row, 0.2),
    (_snap_row, 40),
    (_check_row, True),
    (_text_row, "나중"),
    (_list_row, ["x", "y"]),
    (_optional_row, 0.4),
    (_path_row, "/tmp/a"),
])
def test_set_value_is_silent(make, given):
    _w = make()
    _edited, _typed = _log(_w)
    _w.set_value(given)
    assert (_edited, _typed) == ([], [])
    assert _w.value() == pytest.approx(given)


@pytest.mark.parametrize("make, edit", [
    (_int_row, lambda w: w._slider.setValue(9)),
    (_float_row, lambda w: w._spin.setValue(0.8)),
    (_snap_row, lambda w: w._slider.setValue(40)),
    (_check_row, lambda w: w._box.setChecked(True)),
    (_text_row, lambda w: w._edit.setText("고침")),
    (_list_row, lambda w: w._edit.setText("x, y")),
    (_optional_row, lambda w: w._box.setChecked(True)),
    (_path_row, lambda w: (w._edit.setText("/tmp/b"),
                           w._edit.editingFinished.emit())),
])
def test_human_edit_emits_both(make, edit):
    _w = make()
    _edited, _typed = _log(_w)
    edit(_w)
    assert (len(_edited), len(_typed)) == (1, 1)


def test_set_value_none_clears_optional():
    _w = _optional_row()
    _w.set_value(0.4)
    _w.set_value(None)
    assert _w.value() is None


def test_optional_slider_edit_emits():
    _w = _optional_row()
    _w.set_value(0.4)
    _edited, _typed = _log(_w)
    _w._slider._spin.setValue(0.7)
    assert (len(_edited), _typed) == (1, [pytest.approx(0.7)])


def test_list_row_drops_blank_entries():
    _w = _list_row()
    _w._edit.setText("a, , b,")
    assert _w.value() == ["a", "b"]


# ── 경로 ──────────────────────────────────────────────────────────────────────
def test_refresh_is_not_a_value_change():
    """다시 읽어 달라는 요청과 값이 바뀐 것은 다른 사건."""
    _w = _path_row()
    _edited, _typed = _log(_w)
    _asked: list = []
    _w.refresh.connect(lambda: _asked.append(True))
    _w.refresh.emit()
    assert (_asked, _edited, _typed) == ([True], [], [])


def test_focus_leaving_unchanged_path_is_silent():
    """초점만 옮겨도 `editingFinished` 가 옴 - 값이 그대로면 편집이 아님."""
    _w = _path_row()
    _w.set_value("/tmp/a")
    _edited, _typed = _log(_w)
    _w._edit.editingFinished.emit()
    assert (_edited, _typed) == ([], [])


# ── 스냅 ──────────────────────────────────────────────────────────────────────
def test_snap_pulls_on_drag():
    _w = _snap_row()
    _w._slider.setValue(2)
    assert _w.value() == 0


def test_set_value_does_not_snap():
    """준 값이 조용히 바뀌면 안 됨 - 스냅 폭 안이어도 그대로."""
    _w = _snap_row()
    _w.set_value(2)
    assert _w.value() == 2


def test_readout_follows_both_paths():
    _w = _snap_row()
    _w.set_value(2)
    assert _w._read.text() == "2"
    _w._slider.setValue(50)
    assert _w._read.text() == "50"


def test_spin_follows_slider_when_no_readout():
    _w = _int_row()
    _w._slider.setValue(8)
    assert _w._spin.value() == 8


def test_set_value_clamps_to_range():
    _w = _int_row()
    _w.set_value(99)
    assert _w.value() == 10
