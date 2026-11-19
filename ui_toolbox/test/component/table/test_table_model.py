"""table model - 행 넣기, 붙이기, 거르기, 정렬 사슬, 편집, CSV 줄 흐름.

행은 dict 통째로 듦 - 칸 선언에 없는 키는 안 보일 뿐. 정렬, 거르기는 보이는 순서만 바꿈.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from ui_toolbox.component.table._model import Pattern, Table_model

_COLS = [{"name": "k", "type": "str"},
         {"name": "n", "type": "float", "editable": True},
         {"name": "on", "type": "bool", "editable": True}]


def _shown(m: Table_model) -> list[str]:
    """보이는 차례의 `k`."""
    return [m.row(m.source(_i))["k"] for _i in range(m.rowCount())]


def test_table_model_flow():
    # 단계 : 행 넣기 - 통째로 듦, 원본 차례
    _m = Table_model(_COLS)
    _m.set_rows([{"k": "b", "n": 2.0, "on": True, "extra": 1}, {"k": "a", "n": None}, {"k": "c", "n": 1}])
    assert _shown(_m) == ["b", "a", "c"] and _m.row(0)["extra"] == 1, "set: source order, keeps undeclared keys"

    # 실패 갈래 : 값이 칸 타입과 어긋남
    with pytest.raises(TypeError):
        _m.set_rows([{"k": 3}])
    assert _shown(_m) == ["b", "a", "c"], "set failure: previous rows kept"

    # 단계 : 정렬 - 오름, 내림, 없음 돌리기. None 은 방향과 상관없이 뒤
    _m.cycle(1)
    assert _shown(_m) == ["c", "b", "a"] and _m.headerData(1, Qt.Orientation.Horizontal) == "n ▲", "sort: ascending"
    _m.cycle(1)
    assert _shown(_m) == ["b", "c", "a"], "sort: descending - None last"
    _m.cycle(1)
    assert _shown(_m) == ["b", "a", "c"] and _m.headerData(1, Qt.Orientation.Horizontal) == "n", "sort: none"

    # 단계 : 정렬 사슬 - 다른 칸을 둔 채 더함, 번호 표시
    _m.set_rows([{"k": "b", "n": 1.0}, {"k": "a", "n": 1.0}, {"k": "c", "n": 0.0}])
    _m.cycle(1)
    _m.cycle(0, keep=True)
    assert _shown(_m) == ["c", "a", "b"], "chain: n then k"
    assert _m.headerData(0, Qt.Orientation.Horizontal) == "k ▲2", "chain: rank shown"
    _m.sort(-1)

    # 단계 : 붙이기 - 정렬이 서 있으면 그 자리로
    _m.cycle(1)
    _m.extend([{"k": "d", "n": 0.5}])
    assert _shown(_m) == ["c", "d", "b", "a"], "extend: sorted position"
    _m.sort(-1)

    # 단계 : 거르기 - 부분 일치, 대소문자 무시, * ? 는 자리표, 정규식 글자는 글자
    _m.filter("D")
    assert _shown(_m) == ["d"], "filter: case-insensitive"
    _m.filter("0.?")
    assert set(_shown(_m)) == {"c", "d"}, "filter: ? is one char"
    _m.filter("")
    assert Pattern("a.c").search("abc") is None, "filter: regex chars are literal"

    # 단계 : 편집 - 칸 타입으로 넘김, 검사, bool 은 체크
    _i = _m.index(_m.shown(3), 1)
    assert _m.data(_i, Qt.ItemDataRole.EditRole) == 0.5, "edit: value"
    assert _m.setData(_i, 9.0) and _m.row(3)["n"] == 9.0, "edit: changed"
    with pytest.raises(TypeError):
        _m.setData(_i, "x")
    _m.set_rows([{"k": "a", "n": 1, "on": False}, {"k": "b", "n": None, "on": None}])
    assert _m.data(_m.index(0, 1), Qt.ItemDataRole.EditRole) == 1.0, "edit: int in a float column becomes float"
    _check = _m.index(0, 2)
    assert _m.flags(_check) & Qt.ItemFlag.ItemIsUserCheckable, "check: editable column"
    assert _m.setData(_check, Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole) and _m.row(0)["on"] is True, \
        "check: changed"
    assert not _m.flags(_m.index(1, 2)) & Qt.ItemFlag.ItemIsUserCheckable, "check: none for None"
    assert not _m.flags(_m.index(0, 0)) & Qt.ItemFlag.ItemIsEditable, "edit: off by default"

    # 단계 : CSV 줄 - 머리글은 칸 이름, 값은 보이는 글자
    assert _m.titles() == ["k", "n", "on"] and _m.line(1) == ["b", "", ""], "CSV line"
