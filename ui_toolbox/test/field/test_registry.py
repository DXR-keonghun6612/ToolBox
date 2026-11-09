"""등록표 - 틀린 것은 올릴 때 막힘.

찾을 때 터지면 그 자리를 누가 올렸는지 못 앎. 그래서 검사가 등록 시점에 섬.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from ui_toolbox.field import Field
from ui_toolbox.field.form.widget import Build, Register


def test_lambda_is_refused():
    with pytest.raises(ValueError):
        Register("없는자료형")(lambda spec, label: QWidget())


def test_wrong_arity_is_refused():
    with pytest.raises(TypeError):
        @Register("없는자료형")
        def _one(spec):
            return QWidget()


def test_duplicate_slot_is_refused():
    """말없이 덮으면 어느 쪽이 섰는지 못 앎."""
    with pytest.raises(KeyError):
        @Register("bool")
        def _again(spec, label):
            return QWidget()


def test_empty_slot_returns_none():
    assert Build(Field("blob", dict)) is None


@pytest.mark.parametrize("spec, name", [
    (Field("a", bool), "Check_row"),
    (Field("b", int), "Int_slider_row"),
    (Field("c", float), "Float_slider_row"),
    (Field("d", float | None), "Optional_float_row"),
    (Field("e", str), "Text_row"),
    (Field("f", str, kind="path"), "Path_row"),
    (Field("g", list[str]), "List_row"),
    (Field("h", list[tuple[str, str]]), "Pair_editor"),
    (Field("i", int, editable=False), "Readout_row"),
])
def test_each_slot_builds_its_widget(spec, name):
    assert type(Build(spec)).__name__ == name


def test_labelled_off_drops_the_label():
    """머리줄이 이름을 이미 들면 위젯이 또 달면 안 됨."""
    _spec = Field("가로", int, 3)
    assert Build(_spec).findChild(QLabel) is not None
    assert Build(_spec, labelled=False).findChild(QLabel) is None


@pytest.mark.parametrize("spec, value", [
    (Field("단위따라", float, max=10.0, step=0.0001), 0.6913),
    (Field("선언대로", float, max=5000.0, step=1.0, decimals=6), 1253.104055),
    (Field("켜고끔", float | None, max=10.0, step=0.00001), 1.00546),
])
def test_float_keeps_its_digits(spec, value):
    """스핀이 자릿수만큼만 들고 있음. 모자라면 값이 조용히 반올림되어 저장됨."""
    _w = Build(spec)
    _w.set_value(value)
    assert _w.value() == pytest.approx(value, abs=1e-12)


def test_float_digits_do_not_drop_below_two():
    """자릿수를 안 준 굵은 단위 선언은 예전처럼 둘째 자리."""
    _w = Build(Field("굵음", float, max=10.0, step=1.0))
    _w.set_value(1.25)
    assert _w.value() == pytest.approx(1.25)


def _percent(value: float) -> str:
    return f"{value:.0%}"


def test_readout_shows_the_declared_text():
    """표에서도 폼에서도 같은 선언이면 같은 글자. 값은 그대로 들고 감."""
    _w = Build(Field("비율", float, 0.25, editable=False, display=_percent),
               labelled=False)
    assert (_w.value(), _w.findChild(QLabel).text()) == (0.25, "25%")
