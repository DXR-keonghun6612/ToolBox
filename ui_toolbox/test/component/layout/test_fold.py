"""fold - 구역 붙이기, 접기와 펴기, 번호 밖.

접으면 그 구역의 최대 높이가 머리 높이, 펴면 제한 없음.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from ui_toolbox.component.layout._fold import _MAX_H, Fold


def test_fold_flow():
    # 단계 : 붙이기 - 머리 글자는 title, 펼친 채로
    _f = Fold()
    _f.add(QLabel("a"), "first")
    _f.add(QLabel("b"), "second")
    assert _f.count() == 2, "add: two sections"
    assert _f.widget(0).head.text() == "first", "add: head text"
    assert _f.is_expanded(0) and _f.is_expanded(1), "add: expanded"

    # 단계 : 접기 - 최대 높이를 머리 높이로, 신호
    _got: list = []
    _f.widget(1).toggled.connect(_got.append)
    _f.set_expanded(1, False)
    _sec = _f.widget(1)
    assert _got == [False] and not _f.is_expanded(1), "collapse: toggled False"
    assert _sec.maximumHeight() == _sec.head.sizeHint().height(), "collapse: max height = head height"

    # 단계 : 펴기 - 제한 풂
    _f.set_expanded(1, True)
    assert _sec.maximumHeight() == _MAX_H, "expand: no limit"

    # 실패 갈래 : 번호 밖
    with pytest.raises(IndexError):
        _f.set_expanded(2, True)
    with pytest.raises(IndexError):
        _f.is_expanded(-1)
