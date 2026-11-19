"""table 보기 - 고르기와 open, 머리글 정렬, 거르기 줄, 칸 폭, 메뉴, CSV 파일 흐름.

`open` : table 설정에 붙으면 고른 행이 바뀔 때 행 dict, 칸에 붙으면 그 칸 더블클릭에 그 칸 값.
"""

from __future__ import annotations

from unittest import mock

import pytest
from PySide6.QtWidgets import QFileDialog

from ui_toolbox.component.table._view import _Column_pick, Table_view

_COLS = [{"name": "key", "type": "str", "width": 1},
         {"name": "path", "type": "str", "open": "detail", "width": 3},
         {"name": "n", "type": "int"}]


def test_table_view_flow(tmp_path):
    # 단계 : 짓기
    _v = Table_view(_COLS, open="summary")
    _v.set_rows([{"key": "b", "path": "/b.yaml", "n": 2, "doc": {"x": 1}}, {"key": "a", "path": "/a.yaml", "n": 1}])
    assert not _v._view.rootIsDecorated(), "build: no expand decoration"
    _open: list = []
    _sel: list = []
    _v.open_requested.connect(lambda r, p: _open.append((r, p)))
    _v.selected.connect(_sel.append)

    # 단계 : 고르기 - selected, 행 open
    _v.select(1)
    assert _sel == [1] and _open[-1] == ("summary", _v.rows()[1]), "select: row dict to summary"
    assert _v.current() == 1 and _v.selection() == [1], "select: current, selection"

    # 단계 : 칸 더블클릭 - 칸 open, open 없는 칸은 안 냄
    _dbl: list = []
    _v.double_clicked.connect(lambda at, name: _dbl.append((at, name)))
    _model = _v._model
    _v._view.doubleClicked.emit(_model.index(_model.shown(0), 1))
    assert _open[-1] == ("detail", "/b.yaml") and _dbl[-1] == (0, "path"), "double click: cell value to detail"
    _n = len(_open)
    _v._view.doubleClicked.emit(_model.index(0, 2))
    assert len(_open) == _n, "double click: silent without open"

    # 단계 : 머리글 정렬, 거르기 줄, 초기화
    _v._on_header(2)
    assert [_v.rows()[_i]["key"] for _i in _v.shown_rows()] == ["a", "b"], "header: n ascending"
    _v._filter.setText("b.y")
    assert _v.shown_rows() == [0], "filter bar"
    _v.reset()
    assert _v.shown_rows() == [0, 1] and _v._filter.text() == "", "reset: source order"

    # 단계 : 칸 폭 - 선언 비율, 표 폭에 맞춤, 자투리는 마지막 칸
    _v.resize(600, 300)
    _v.show()
    _widths = [_v._view.columnWidth(_c) for _c in range(3)]
    assert sum(_widths) == _v._view.viewport().width(), f"width: sum fits the view {_widths}"
    assert _widths[1] > _widths[0] * 2, f"width: ratio 1 : 3 kept {_widths}"
    _v.hide()

    # 단계 : CSV - 머리글은 칸 이름, 값은 보이는 글자, BOM, 고른 칸만
    _path = tmp_path / "t.csv"
    assert _v.write_csv(_path) == 2, "CSV: row count"
    assert _path.read_text(encoding="utf-8-sig").splitlines() == ["key,path,n", "b,/b.yaml,2", "a,/a.yaml,1"], "CSV: content"
    assert _path.read_bytes().startswith(b"\xef\xbb\xbf"), "CSV: BOM"
    _v.write_csv(_path, [1], ["n", "key"])
    assert _path.read_text(encoding="utf-8-sig").splitlines() == ["key,n", "a,1"], "CSV: picked columns in table order"

    # 단계 : 메뉴 - 글자가 행 수를 따름, 항목은 소비처가 뺌
    _v.select(0)
    _v.menu.aboutToShow.emit()
    assert _v.export_action.text().endswith("1 행") and _v.export_action.isEnabled(), "menu: export text follows rows"
    _v.menu.removeAction(_v.export_action)
    assert _v.menu.actions() == [], "menu: consumer removes items"

    # 단계 : 칸 고르기 - 처음엔 다, 하나도 없으면 확인 꺼짐, 고른 칸으로 씀
    _pick = _Column_pick(["key", "path", "n"], 2, _v)
    assert _pick.names() == ["key", "path", "n"] and _pick._ok.isEnabled(), "pick: all checked"
    for _b in _pick._boxes:
        _b.setChecked(False)
    assert not _pick._ok.isEnabled(), "pick: ok off without columns"
    _pick._boxes[2].setChecked(True)
    _out = tmp_path / "picked.csv"
    with mock.patch.object(_Column_pick, "exec", return_value=1), \
            mock.patch.object(_Column_pick, "names", return_value=["n"]), \
            mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(_out), "")):
        _v._on_export()
    assert _out.read_text(encoding="utf-8-sig").splitlines() == ["n", "2"], "export: picked column, picked row"

    # 실패 갈래 : 없는 칸
    with pytest.raises(KeyError):
        _v.write_csv(_path, None, ["nothing"])
