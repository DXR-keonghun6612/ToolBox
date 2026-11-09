"""행 여럿을 미는 것 - 같은 계약, payload 만 다름.

칸 위젯은 폼과 같은 등록표에서 옴. 자료형이 늘 때 고치는 자리가 둘이 되면 안 됨.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from ui_toolbox.field import Field, Rows, Stack_view, Table_view, Value
from ui_toolbox.field.form.layout import Pair_editor

_FIELDS = [Field("이름", str), Field("켬", bool), Field("수", int, 0, max=10)]
_ROWS = [{"이름": "a", "켬": True, "수": 3}, {"이름": "b", "켬": False, "수": 7}]


def _stack() -> Stack_view:
    return Stack_view(Rows(_FIELDS, _ROWS))


def _table() -> Table_view:
    return Table_view(Rows(_FIELDS, _ROWS))


@pytest.mark.parametrize("make", [_stack, _table, Pair_editor])
def test_row_pushers_share_the_contract(make):
    assert isinstance(make(), Value)


@pytest.mark.parametrize("make", [_stack, _table])
def test_value_round_trips(make):
    _w = make()
    assert _w.value() == _ROWS


@pytest.mark.parametrize("make", [_stack, _table])
def test_set_value_is_silent(make):
    _w = make()
    _log: list = []
    _w.edited.connect(lambda: _log.append(True))
    _w.set_value([{"이름": "z"}])
    assert (_log, _w.value()) == ([], [{"이름": "z"}])


# ── 칸 위젯이 등록표에서 옴 ───────────────────────────────────────────────────
@pytest.mark.parametrize("at, name", [
    (0, "Text_row"), (1, "Check_row"), (2, "Int_slider_row"),
])
def test_cell_comes_from_the_registry(at, name):
    _w = _stack()
    _cell = _w._cell(0, _FIELDS[at])
    assert type(_cell).__name__ == name


def test_cell_carries_the_row_value():
    _w = _stack()
    assert _w._cell(1, _FIELDS[2]).value() == 7


def test_missing_column_falls_back_to_the_declaration():
    """행에 그 칸이 없을 때 무엇을 쓸지는 `Field.default` 가 이미 듦."""
    _w = Stack_view(Rows(_FIELDS, [{"이름": "a"}]))
    assert _w._cell(0, Field("수", int, 5, max=10)).value() == 5


def test_cell_wears_no_label():
    """머리줄이 칸 이름을 이미 듦 - 칸이 또 달면 두 번 나옴."""
    _w = _stack()
    assert _w._cell(0, _FIELDS[0]).findChild(QLabel) is None


def test_readonly_column_gets_a_readout():
    _w = _stack()
    assert type(_w._cell(0, Field("잠김", str, editable=False))).__name__ == "Readout_row"


def test_unknown_column_type_raises():
    with pytest.raises(TypeError):
        _stack()._cell(0, Field("blob", dict))


# ── 쌍 편집기 ─────────────────────────────────────────────────────────────────
def test_pairs_round_trip():
    _p = Pair_editor()
    _p.set_value([("k", "v"), ("k", "w")])       # 중복 key 를 허용
    assert _p.value() == [("k", "v"), ("k", "w")]


def test_pairs_drop_blank_keys():
    _p = Pair_editor()
    _p.set_value([("k", "v"), ("", "버려짐")])
    assert _p.value() == [("k", "v")]


def test_pair_fields_come_from_the_caller():
    """배치가 선언을 안 지음 - 소비처가 폭 · 문구를 정함."""
    _p = Pair_editor(fields=[Field("key", str, label="이름", width=140),
                             Field("value", str, label="값")])
    assert [_f.title() for _f in _p._data.fields] == ["이름", "값"]
