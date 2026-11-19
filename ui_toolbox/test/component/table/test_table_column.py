"""table 칸 선언 - 검사, 값 검사, 보일 글자, 정렬 열쇠 흐름.

칸 선언 : dict - `name`, `type`(bool, int, float, str), `editable`(없으면 거짓), `open`, `width`(없으면 None).
"""

from __future__ import annotations

import pytest

from ui_toolbox.component.table._column import Blank, Check_columns, Check_value, Order, Text


def test_table_column_flow():
    # 단계 : 검사 - 빠진 선택 키를 채운 사본
    _cols = Check_columns([{"name": "k", "type": "str", "open": "detail", "width": 3}, {"name": "n", "type": "float"}])
    assert _cols[0] == {"name": "k", "type": "str", "editable": False, "open": "detail", "width": 3}, \
        "check: optional keys filled"
    assert _cols[1]["editable"] is False and _cols[1]["open"] is None and _cols[1]["width"] is None, \
        "check: defaults False, None"

    # 실패 갈래 : 검사
    for _bad in ([{"name": "a"}], [{"name": "a", "type": "str", "size": 3}],
                 [{"name": "a", "type": "str"}, {"name": "a", "type": "int"}], [{"name": "a", "type": "list"}]):
        with pytest.raises(ValueError):
            Check_columns(_bad)
    for _bad in ([{"name": "a", "type": "str", "editable": 1}], [{"name": "a", "type": "str", "open": 3}],
                 [{"name": "a", "type": "str", "width": 0}], [{"name": "a", "type": "str", "width": 1.5}],
                 [{"name": "a", "type": "str", "width": True}]):
        with pytest.raises(TypeError):
            Check_columns(_bad)

    # 단계 : 값 검사 - 타입이 같아야 함, float 칸은 int 도, None 은 늘 맞음
    _int, _float = Check_columns([{"name": "i", "type": "int"}, {"name": "f", "type": "float"}])
    for _col, _v in ((_int, 3), (_int, None), (_float, 1.5), (_float, 1)):
        Check_value(_col, _v)

    # 실패 갈래 : 값 검사 - bool 은 int 칸에, bool 은 float 칸에 안 들어감
    for _col, _v in ((_int, True), (_int, 3.0), (_int, "3"), (_float, True), (_float, "1")):
        with pytest.raises(TypeError):
            Check_value(_col, _v)

    # 단계 : 보일 글자, 빈 값
    assert Text(_float, None) == "" and Text(_float, 1.5) == "1.5", "display text"
    assert [Blank(_c) for _c in Check_columns([{"name": t, "type": t} for t in ("bool", "int", "float", "str")])] \
        == [False, 0, 0.0, ""], "blank values"

    # 단계 : 정렬 열쇠 - None 은 뒤
    assert sorted([2.5, None, 1, 0.5], key=lambda v: Order(_float, v)) == [0.5, 1, 2.5, None], "order: numbers, None last"
