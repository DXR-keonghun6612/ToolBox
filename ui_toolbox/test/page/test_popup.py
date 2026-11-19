"""popup - 두 축(modal, result), 확인 / 취소 줄, 본문 자리."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from ui_toolbox.page import Popup


def test_popup_flow():
    # 단계 : 결과 없음 - 버튼 줄 없음, 막지 않음
    _plain = Popup()
    assert not _plain.is_blocking(), "no result: not blocking"
    assert _plain.findChild(QDialogButtonBox) is None, "no result: no button row"
    _plain.open()
    assert _plain.isVisible(), "no result: open() shows"
    _plain.close()

    # 단계 : 결과 있음 - 확인이 accepted
    _ask = Popup(modal=True, result=True)
    _row = _ask.findChild(QDialogButtonBox)
    assert _row is not None and _ask.is_blocking(), "result: button row, blocking"
    _got: list = []
    _ask.accepted.connect(lambda: _got.append("ok"))
    _row.button(QDialogButtonBox.StandardButton.Ok).click()
    assert _got == ["ok"], "result: Ok -> accepted"
    assert _ask.layout().itemAt(0).widget() is _ask.body, "result: body above the button row"

    # 단계 : 크기
    _sized = Popup(size=[300, 200])
    assert (_sized.width(), _sized.height()) == (300, 200), "size: initial size"

    # 실패 갈래 : bool 아님, 크기 꼴
    with pytest.raises(TypeError):
        Popup(modal=1)
    with pytest.raises(ValueError):
        Popup(size=[300])
