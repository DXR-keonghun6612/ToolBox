"""component 등록표 - 찾기, 소비처 등록, control 계약 이행 흐름.

키는 클래스 이름. `Registry` 는 목록 · 지우기가 없어 기대한 이름이 다 있는지만 봄. 소비처 등록은 시험 끝에 표의 속에서
되돌림 - 다른 시험에 안 새게.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from ui_toolbox.component import REGISTRY, register

#: 표에 있어야 할 것.
_CONTROLS = ["Bool_check", "Bool_toggle", "Int_spin", "Float_spin", "Int_slider", "Float_slider", "Str_text",
             "List_text", "Path_text", "Paths_text", "Choice_combo", "Choice_radio", "Choices_check", "Readout"]
_OTHERS = ["Table_view", "Tree_view", "Progress_bar", "Raster_editor", "Fold"]


def test_registry_flow():
    # 단계 : 찾기 - 키는 클래스 이름, 위젯
    for _name in _CONTROLS + _OTHERS:
        _cls = REGISTRY.Get(_name)
        assert _cls.__name__ == _name, f"get: key {_name} vs class name {_cls.__name__}"
        assert issubclass(_cls, QWidget), f"get: {_name} is not a widget"

    # 단계 : control 계약 이행 - 이름 규약 셋
    for _name in _CONTROLS:
        for _attr in ("value", "set_value", "value_changed"):
            assert hasattr(REGISTRY.Get(_name), _attr), f"contract: {_name} has no {_attr}"

    # 실패 갈래 : 없는 이름, 소문자 key 아님
    with pytest.raises(KeyError):
        REGISTRY.Get("Nothing")
    with pytest.raises(KeyError):
        REGISTRY.Get("table_view")

    # 단계 : 소비처 등록
    class Pose_edit(QWidget):
        pass

    try:
        assert register(Pose_edit) is Pose_edit, "consumer: returns the class - usable as a decorator"
        assert REGISTRY.Get("Pose_edit") is Pose_edit, "consumer: found by class name"

        # 실패 갈래 : 겹침, 위젯 아님, 클래스 아님
        with pytest.raises(KeyError):
            register(Pose_edit)
        with pytest.raises(KeyError):
            register(type("Table_view", (QWidget,), {}))
        with pytest.raises(TypeError):
            register(type("Plain", (), {}))
        with pytest.raises(TypeError):
            register(Pose_edit())
    finally:
        REGISTRY._module_dict.pop("Pose_edit", None)
