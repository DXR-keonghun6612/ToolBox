"""raster 편집기 - 짓기부터 사람의 조작까지 한 흐름.

입력 영상 : `(100, 200, 3)` uint8, 화면 400 x 300 - 맞춤 배율 약 2. 조작은 `QTest` 로 viewport 에.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout
from PySide6.QtTest import QTest

from ui_toolbox.component.editor.raster._editor import Raster_editor


def _drag(vp, start: QPoint, end: QPoint, steps: int = 4, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    """누르고 몇 번 움직여 뗌."""
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, modifier, start)
    for _i in range(1, steps + 1):
        QTest.mouseMove(vp, start + (end - start) * _i / steps)
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, modifier, end)


def test_raster_editor_flow():
    # 단계 : 짓기
    _e = Raster_editor(["box", "polygon", "brush", "eraser"], brush_radius=8, brush_step=2.0, min_size=5)
    _e.resize(400, 300)
    _e.show()
    _e.activateWindow()
    _e.set_image(np.zeros((100, 200, 3), np.uint8))
    QApplication.processEvents()
    _vp = _e._view.viewport()
    _vp.setFocus()
    _c = _vp.rect().center()
    _got: list = []
    _e.box.connect(lambda b, k: _got.append((k, b)))
    _e.vertices.connect(lambda v, c, r, k: _got.append((k, v, c, r)))
    _e.picked.connect(lambda p, t, k: _got.append((k, p, t)))
    assert _e.tool() == "", "build: starts in view"
    assert list(_e._buttons) == ["view", "box", "polygon", "brush", "eraser"], "build: toolbar order"

    # 실패 갈래 : 짓기
    for _kw in (dict(tools=["lasso"]), dict(tools=["box", "box"]), dict(toolbar="middle"), dict(options="left")):
        with pytest.raises(ValueError):
            Raster_editor(**_kw)
    assert list(Raster_editor()._buttons) == [], "build: no tools, no view button"

    # 단계 : 자리 - 기본 위 한 줄, 왼쪽이면 세로, None 이면 안 놓음
    assert _e.toolbar.parent() is _e and _e.options.parent() is _e, "place: placed inside by default"
    _left = Raster_editor(tools=["box"], toolbar="left", options=None)
    assert isinstance(_left.toolbar.layout(), QVBoxLayout), "place: left toolbar is vertical"
    assert _left.options.parent() is None, "place: None leaves options to the consumer"

    # 단계 : 보기 - 클릭은 pick, Shift 는 토글
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, pos=_c)
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, _c)
    assert [(_g[0], _g[2]) for _g in _got] == [("pick", False), ("pick", True)], "view: pick, toggle"
    _got.clear()

    # 단계 : 보기 - 끌면 올가미, 끄는 동안 외곽선
    QTest.mousePress(_vp, Qt.MouseButton.LeftButton, pos=_c)
    for _d in (15, 30, 45):
        QTest.mouseMove(_vp, _c + QPoint(_d, _d // 3))
    assert _e._lasso_preview._dark.path().elementCount() > 0, "lasso: outline while dragging"
    QTest.mouseRelease(_vp, Qt.MouseButton.LeftButton, pos=_c + QPoint(45, 15))
    assert _got and _got[-1][0] == "lasso" and _got[-1][2] is True, "lasso: closed vertices"
    assert _e._lasso_preview._dark.path().elementCount() == 0, "lasso: outline cleared on release"
    _got.clear()

    # 단계 : 상자 - 역치보다 작으면 안 냄
    QTest.keyClick(_vp, Qt.Key.Key_R)
    assert _e.tool() == "box", "box: shortcut R"
    _drag(_vp, _c, _c + QPoint(4, 4))
    assert _got == [], "box: silent below threshold (5 px)"
    _drag(_vp, _c, _c + QPoint(40, 30))
    assert _got[-1][0] == "box" and _got[-1][1].shape == (2, 2), "box: (2, 2)"
    assert np.all(_got[-1][1][1] > _got[-1][1][0]), "box: min, max corner order"
    _got.clear()

    # 단계 : 다각형 - 우클릭으로 점 빼기, 역치, C 로 닫음
    QTest.keyClick(_vp, Qt.Key.Key_P)
    _poly = _e._tools["polygon"]
    for _p in (QPoint(0, 0), QPoint(3, 0), QPoint(3, 3), QPoint(60, 60)):
        QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, pos=_c + _p)
    QTest.mouseClick(_vp, Qt.MouseButton.RightButton, pos=_c)
    assert len(_poly._points) == 3, "polygon: right click drops the last point"
    QTest.keyClick(_vp, Qt.Key.Key_C)
    assert _got == [] and len(_poly._points) == 3, "polygon: below threshold keeps points open"
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, pos=_c + QPoint(40, 40))
    QTest.keyClick(_vp, Qt.Key.Key_Return)
    assert _got[-1][0] == "polygon" and _got[-1][1].shape == (4, 2) and _got[-1][2] is True, "polygon: Enter closes"
    _got.clear()

    # 단계 : 브러시 - 강조색 옅게, 뗄 때 한 번
    QTest.keyClick(_vp, Qt.Key.Key_B)
    QTest.mousePress(_vp, Qt.MouseButton.LeftButton, pos=_c)
    QTest.mouseMove(_vp, _c + QPoint(20, 0))
    _stroke = _e._tools["brush"]
    assert _stroke._preview._fill._items, "brush: preview while dragging"
    assert _got == [], "brush: silent while dragging"
    QTest.mouseRelease(_vp, Qt.MouseButton.LeftButton, pos=_c + QPoint(20, 0))
    assert _got[-1][0] == "brush" and _got[-1][2] is False and _got[-1][3] == 8.0, "brush: path, open, radius"
    _got.clear()

    # 단계 : 지우개 - 원본 덮기, 뗄 때 한 번
    QTest.keyClick(_vp, Qt.Key.Key_E)
    _drag(_vp, _c, _c + QPoint(0, 20))
    assert len(_got) == 1 and _got[0][0] == "eraser", "eraser: once on release"
    _got.clear()

    # 단계 : 반경 단축키 - 고정 값 / 확대 비율, 최소 1 px
    _spin = _stroke._radius
    for _zoom, _want in ((8.0, 9), (0.25, 16)):
        _e.set_zoom(_zoom)
        _spin.setValue(8)
        QTest.keyClick(_vp, Qt.Key.Key_BracketRight)
        assert _spin.value() == _want, f"radius: ] at zoom {_zoom} -> {_spin.value()}"
    _e.reset_zoom()
    QApplication.processEvents()

    # 단계 : 잠금 - 도구, 토글, 올가미는 막고 하나씩 고르기는 둠
    _e.setEnabled(False)
    assert not _e.isEnabled() and not _e.toolbar.isEnabled(), "lock: editing blocked, toolbar off"
    _drag(_vp, _c, _c + QPoint(0, 30))
    assert _got == [], "lock: tools blocked"
    _e.set_view()
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, _c)
    _drag(_vp, _c, _c + QPoint(40, 20))
    assert _got == [], "lock: toggle, lasso blocked"
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, pos=_c)
    assert [_g[0] for _g in _got] == ["pick"], "lock: single pick stays"
    _e.setEnabled(True)
    _got.clear()

    # 단계 : 조준 - 대상이 바뀔 때만 진행 중 조작을 버림
    _e.set_tool("polygon")
    _e.aim("img1")
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, pos=_c)
    _e.aim("img1")
    assert len(_poly._points) == 1, "aim: same target keeps"
    _e.aim("img2")
    assert _poly._points == [] and _e.tool() == "polygon", "aim: new target clears, tool stays"

    # 단계 : Esc - 그리던 것이 있으면 취소, 없으면 보기로
    QTest.mouseClick(_vp, Qt.MouseButton.LeftButton, pos=_c)
    QTest.keyClick(_vp, Qt.Key.Key_Escape)
    assert _poly._points == [] and _e.tool() == "polygon", "Esc: cancels drawing"
    QTest.keyClick(_vp, Qt.Key.Key_Escape)
    assert _e.tool() == "", "Esc: back to view"

    # 단계 : 보기 버튼 - 도구와 배타
    QTest.keyClick(_vp, Qt.Key.Key_B)
    _e._buttons["view"].click()
    _checked = [_k for _k, _b in _e._buttons.items() if _b.isChecked()]
    assert _e.tool() == "" and _checked == ["view"], "view button: only view checked"
