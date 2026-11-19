"""build - config 를 읽어 짓고 놓는 흐름. 배치, 묶음과 경로 찾기, link, action, items 파일, 영역 이름, style, 실패 갈래.

입력 `test/resource/page/detail.yaml` : `items` 맵 하나 - `note`(qt_QLabel), `doc`(Tree_view, `open: {path: pick}`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QTabWidget, QWidget

from ui_toolbox.component import Fold, Table_view, Tree_view
from ui_toolbox.page import Fill, Popup

_RESOURCE = Path(__file__).parents[1] / "resource" / "page"

_TABLE = {"class": "Table_view", "args": {"columns": [{"name": "k", "type": "str", "open": "detail"}], "open": "pick"}}

_CONFIG = {
    "title": "Records",
    "class": "qt_QSplitter",
    "link": {
        "pick": {"title": "Pick columns", "class": "qt_QVBoxLayout", "args": {"modal": True, "result": True},
                 "items": {"columns": {"class": "Choices_check", "args": {"options": ["a", "b"]}}}},
    },
    "items": {
        "records": {
            "class": "qt_QTabWidget",
            "items": {
                "list": {"class": "qt_QVBoxLayout", "args": {"spacing": 3}, "items": {"table": _TABLE}},
                "side": {"title": "Side view", "class": "Fold",
                         "items": {"memo": {"title": "Memo", "class": "qt_QLabel", "args": {"text": "m"}}}},
            },
        },
        "detail": {"class": "qt_QVBoxLayout", "items": "detail.yaml"},
        "canvas": {
            "class": "qt_QVBoxLayout",
            "action": {"menu": {"file": {"items": {"open": {"title": "Open", "args": {"shortcut": "Ctrl+O"}}}}},
                       "context": {"export": {"title": "Export"}}},
            "items": {"save": {"class": "qt_QPushButton", "args": {"text": "Save"}},
                      "size": {"class": "qt_QLabel", "args": {"text": "same name as a Qt method"}}},
            "style": {"save": {"min-width": "80px"}},
        },
    },
    "style": {"Table_view": {"font-size": "12px"}, "records table": {"color": "red"}},
}


def _fill(config: dict) -> QWidget:
    _w = QWidget()
    Fill(_w, config, _RESOURCE)
    return _w


def test_build_flow():
    _page = _fill(_CONFIG)

    # 단계 : root - 창 제목, 배치
    assert _page.windowTitle() == "Records", "root: window title"
    assert isinstance(_page.layout().itemAt(0).widget(), QSplitter), "root: layout widget held inside"

    # 단계 : 묶음과 경로 - items 묶음, find 가 segment 마다 items 로
    _records = _page.items.records
    assert isinstance(_records, QTabWidget) and _records.objectName() == "records", "names: layout widget itself"
    assert _page.items.find("records.list.table") is _records.items.list.items.table, "find: same object as names"
    assert isinstance(_page.items.find("records.list.table"), Table_view), "find: third segment"
    assert _page.items.find("canvas.size").text() == "same name as a Qt method", "names: no clash with Qt names"

    # 단계 : 배치 - 탭 글자, QLayout 인자, fold 머리
    assert [_records.tabText(_i) for _i in range(_records.count())] == ["list", "Side view"], "layout: tab text"
    assert _records.items.list.layout().spacing() == 3, "layout: QLayout constructor args"
    _side = _records.items.side
    assert isinstance(_side, Fold) and _side.widget(0).head.text() == "Memo", "layout: fold head = title"

    # 단계 : items 파일 - 그 node 를 적은 파일의 폴더 기준
    assert _page.items.find("detail.note").text() == "detail", "items file: note"
    assert isinstance(_page.items.find("detail.doc"), Tree_view), "items file: doc"

    # 단계 : link - popup, 배치에 안 듦, 창 꼴
    _pick = _page.link.pick
    assert isinstance(_pick, Popup) and _pick.is_blocking(), "link: layout class builds Popup with its args"
    assert _pick.isWindow() and _pick.parent() is _page, "link: window under its node"
    assert _pick.windowTitle() == "Pick columns" and _pick.items.columns.value() == [], "link: title, names"

    # 단계 : action - menu 의 하위 메뉴, context, 묶음
    _canvas = _page.items.canvas
    _open = _canvas.action.open
    assert _open.text() == "Open" and _open.shortcut().toString() == "Ctrl+O", "action: title, args"
    assert _canvas.layout().menuBar() is not None, "action: menu bar"
    assert _canvas.contextMenuPolicy() == Qt.ContextMenuPolicy.ActionsContextMenu, "action: context policy"
    assert _canvas.action.export in _canvas.actions(), "action: attached to context"

    # 단계 : style - root 와 제 style 이 있는 node 에 시트, node key 는 #key
    assert "Table_view { font-size: 12px; }" in _page.styleSheet(), "style: class name kept"
    assert "#records #table { color: red; }" in _page.styleSheet(), "style: keys in a descendant selector"
    assert "#save { min-width: 80px; }" in _canvas.styleSheet(), "style: node style"
    assert "Table_view" in _canvas.styleSheet(), "style: inherits from above"
    assert _pick.styleSheet() == _page.styleSheet(), "style: popup is a window - gets what it receives"
    assert _records.styleSheet() == "", "style: no sheet without own style"


def _bad(config: dict, error: type, case: str) -> None:
    with pytest.raises(error):
        _fill(config)


def test_build_fail_flow():
    _layout = {"class": "qt_QVBoxLayout"}

    # 실패 갈래 : root
    _bad({"items": {}}, ValueError, "root without class")
    _bad({"class": "qt_QLabel"}, TypeError, "root class not a layout")
    _bad({"class": "qt_QVBoxLayout", "items": {"part": {"class": "qt_QLabel"}}}, ValueError, "component under root")

    # 실패 갈래 : node 칸, 이름
    _bad({**_layout, "size": 1}, ValueError, "unknown field")
    _bad({**_layout, "items": {"part": {**_layout, "args": [1]}}}, TypeError, "args type")
    _bad({**_layout, "items": {"part": {"class": "Nothing"}}}, KeyError, "unregistered class")
    _bad({**_layout, "items": {"part": {"class": "qt_Nothing"}}}, KeyError, "not in PySide6")
    _bad({**_layout, "items": {"part": {"args": {}}}}, ValueError, "no class")
    _bad({**_layout, "items": {"part": {**_layout, "items": {"inner": {"class": "qt_QLabel", "args": {"nope": 1}}}}}},
         TypeError, "constructor args")

    # 실패 갈래 : key
    _bad({**_layout, "items": {"find": _layout}}, KeyError, "Names method name")
    _bad({**_layout, "items": {"_x": _layout}}, ValueError, "leading underscore")
    _bad({**_layout, "items": {"part": {**_layout, "items": {"inner": {"class": "qt_QLabel", "items": {}}}}}},
         ValueError, "items on a non-layout node")

    # 실패 갈래 : link
    _bad({**_layout, "link": {"p": {"class": "qt_QLabel"}}}, TypeError, "link class neither layout nor popup")

    # 실패 갈래 : 영역 이름 - 없는 이름, 형제 node 의 link 는 안 보임
    _table = {**_layout, "items": {"table": {"class": "Table_view", "args": {"columns": [], "open": "nowhere"}}}}
    _bad({**_layout, "items": {"part": _table}}, KeyError, "unknown region")
    _sibling = {**_layout, "link": {"pick": {"class": "qt_QVBoxLayout"}}}
    _seeker = {**_layout, "items": {"table": {"class": "Table_view", "args": {"columns": [], "open": "pick"}}}}
    _bad({**_layout, "items": {"own": _sibling, "other": _seeker}}, KeyError, "sibling link not visible")

    # 실패 갈래 : action
    _bad({**_layout, "action": {"tool": {}}}, ValueError, "unknown place")
    _bad({**_layout, "action": {"menu": {"a": {}}, "context": {"a": {}}}}, KeyError, "duplicate action key")
    _bad({**_layout, "items": {"part": {"class": "qt_QSplitter", "action": {"menu": {"a": {}}}}}},
         TypeError, "menu bar without QLayout")

    # 실패 갈래 : items 파일, style
    _bad({**_layout, "items": "nothing.yaml"}, ValueError, "missing file")
    _bad({**_layout, "items": {"Fold": _layout}, "style": {"Fold": {"color": "red"}}}, KeyError,
         "selector both key and class name")


def test_find_flow():
    _page = _fill(_CONFIG)

    # 실패 갈래 : 없는 key, 중간 segment 가 container 아님
    with pytest.raises(KeyError):
        _page.items.find("records.nothing")
    with pytest.raises(KeyError):
        _page.items.find("records.list.table.inner")
