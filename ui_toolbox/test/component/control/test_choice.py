"""고르기 control - 기본, None 이면 기본으로, 후보 밖 실패, 줄 방향 흐름.

기본 : `default`(값) / `default_at`(번호) 중 하나. 하나 고르기는 꼭 하나, 여럿 고르기는 둘 다 안 주면 안 고름.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QBoxLayout

from ui_toolbox.component.control._choice import Choice_combo, Choice_radio, Choices_check


def test_choice_flow():
    # 단계 : 기본 - 값, 번호
    assert Choice_combo([1, 2, 3], default=2).value() == 2, "default: value"
    assert Choice_radio(["x", "y", "z"], default_at=2).value() == "z", "default: index"
    assert Choices_check(["x", "y"]).value() == [], "default: multi picks nothing when unset"
    assert Choices_check(["x", "y", "z"], default_at=[2, 0]).value() == ["x", "z"], "default: multi in option order"

    # 실패 갈래 : 기본
    for _make in (lambda: Choice_radio(["x"]), lambda: Choice_radio(["x"], default="x", default_at=0),
                  lambda: Choice_combo([1], default_at=5), lambda: Choices_check(["x"], default=["x"], default_at=[0])):
        with pytest.raises(ValueError):
            _make()

    # 단계 : None 이면 기본으로
    _c = Choice_combo([1, 2, 3], default=2)
    _c.set_value(3)
    _c.set_value(None)
    assert _c.value() == 2, "None: single back to default"
    _k = Choices_check(["x", "y"], default_at=[1])
    _k.set_value(["x"])
    _k.set_value(None)
    assert _k.value() == ["y"], "None: multi back to default"

    # 실패 갈래 : 후보 밖
    with pytest.raises(ValueError):
        _c.set_value(9)
    with pytest.raises(ValueError):
        _k.set_value(["q"])

    # 단계 : 줄 방향 - vertical bool
    _h = Choice_radio(["x", "y"], default="x")
    _v = Choices_check(["x", "y"], vertical=True)
    assert _h.layout().direction() == QBoxLayout.Direction.LeftToRight, "direction: horizontal by default"
    assert _v.layout().direction() == QBoxLayout.Direction.TopToBottom, "direction: vertical"

    # 실패 갈래 : bool 아닌 vertical
    for _bad in ("vertical", None, 1):
        with pytest.raises(TypeError):
            Choice_radio(["x"], default="x", vertical=_bad)
