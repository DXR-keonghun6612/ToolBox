"""표 - 보이는 글자는 선언이, 순서는 값이 정함. 행을 붙여도 모델이 안 풀림.

행이 몇 만씩 붙는 소비처가 있음. 붙일 때마다 리셋이면 고른 자리가 풀리고 비용이 행 수를 따라감.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ui_toolbox.field import Field, Rows, Table_view


def _hash(value) -> str:
    """글자 순서가 값 순서와 어긋나게 - 글자로는 `#10` 이 `#9` 앞."""
    return f"#{value}"


_FIELDS = [Field("이름", str, editable=False),
           Field("수", int, editable=False, display=_hash)]


def _table(rows: list[dict]) -> Table_view:
    return Table_view(Rows(_FIELDS, rows), add_label="")


def _names(table: Table_view) -> list[str]:
    """보이는 순서의 첫 칸."""
    _m = table._model
    return [_m.data(_m.index(_r, 0)) for _r in range(_m.rowCount())]


# ── 보이는 글자 ───────────────────────────────────────────────────────────────
def test_display_role_uses_the_declaration():
    _m = _table([{"이름": "a", "수": 9}])._model
    _at = _m.index(0, 1)
    assert _m.data(_at, Qt.ItemDataRole.DisplayRole) == "#9"
    assert _m.data(_at, Qt.ItemDataRole.EditRole) == "9"


def test_filter_reads_the_shown_text():
    _t = _table([{"이름": "a", "수": 9}, {"이름": "b", "수": 10}])
    _t._model.filter("#9")
    assert _names(_t) == ["a"]


def test_sort_reads_the_value():
    """글자로 정렬하면 `#10` 이 앞. 수는 수로."""
    _t = _table([{"이름": "a", "수": 10}, {"이름": "b", "수": 9}])
    _t._model.sort(1)
    assert _names(_t) == ["b", "a"]


# ── 정렬 사슬 ─────────────────────────────────────────────────────────────────
_CHAIN = [{"이름": _n, "수": _v} for _n, _v in [("b", 1), ("a", 2), ("c", 1), ("d", 2)]]


def _headers(table: Table_view) -> list[str]:
    _m = table._model
    return [_m.headerData(_c, Qt.Orientation.Horizontal) for _c in range(_m.columnCount())]


def test_cycle_goes_none_up_down_none():
    _t = _table(_CHAIN)
    _seen = []
    for _ in range(3):
        _t._model.cycle(1)
        _seen.append((_names(_t), _headers(_t)[1]))
    assert _seen == [(["b", "c", "a", "d"], "수 ▲"),
                     (["a", "d", "b", "c"], "수 ▼"),
                     (["b", "a", "c", "d"], "수")]


def test_plain_cycle_drops_the_other_column():
    _t = _table(_CHAIN)
    _t._model.cycle(1)
    _t._model.cycle(0)
    assert (_names(_t), _headers(_t)) == (["a", "b", "c", "d"], ["이름 ▲", "수"])


def test_keep_chains_and_numbers_the_headers():
    """앞 칸이 같은 행은 뒤 칸 순서로. 번호는 사슬일 때만."""
    _t = _table(_CHAIN)
    _t._model.cycle(1)
    _t._model.cycle(0, keep=True)
    assert (_names(_t), _headers(_t)) == (["b", "c", "a", "d"], ["이름 ▲2", "수 ▲1"])
    _t._model.cycle(0, keep=True)
    assert (_names(_t), _headers(_t)) == (["c", "b", "d", "a"], ["이름 ▼2", "수 ▲1"])
    _t._model.cycle(1, keep=True)          # 앞 칸이 내림으로 돌아도 자리는 그대로
    assert _headers(_t) == ["이름 ▼2", "수 ▼1"]
    _t._model.cycle(1, keep=True)          # 앞 칸이 빠지면 남은 칸이 하나라 번호가 없음
    assert (_names(_t), _headers(_t)) == (["d", "c", "b", "a"], ["이름 ▼", "수"])


def test_reset_clears_filter_and_sort():
    _t = _table(_CHAIN)
    _t._filter.setText("?")
    _t._filter.setText("a")
    _t._model.cycle(0, keep=True)
    _t.reset()
    assert (_names(_t), _headers(_t), _t._filter.text()) == (["b", "a", "c", "d"], ["이름", "수"], "")


@pytest.mark.parametrize("order", [Qt.SortOrder.AscendingOrder,
                                   Qt.SortOrder.DescendingOrder])
def test_extend_under_a_chain_lands_where_a_rebuild_would(order):
    _t = _table(_CHAIN)
    _t._model.sort(1, order)
    _t._model.cycle(0, keep=True)
    _t._model.cycle(0, keep=True)          # 수 -> 이름 내림
    _t.extend([{"이름": _n, "수": _v}
               for _n, _v in [("a", 1), ("e", 2), ("c", 0), ("b", None), ("f", 1)]])
    _inserted = list(_t._model._order)
    _t._model._rebuild()
    assert _inserted == _t._model._order


# ── 조작 줄 ───────────────────────────────────────────────────────────────────
def _editable(rows: list[dict]) -> Table_view:
    return Table_view(Rows(_FIELDS, rows))


def test_remove_edits_once():
    _t = _editable(_CHAIN)
    _edits = []
    _t.edited.connect(lambda: _edits.append(True))
    _t.select(1)
    _t._on_remove()
    assert (_names(_t), len(_edits)) == (["b", "c", "d"], 1)


def test_clear_asks_first(monkeypatch):
    _t = _editable(_CHAIN)
    _asked = []
    _answer = [QMessageBox.StandardButton.No]

    def _question(*_a, **_k):
        _asked.append(True)
        return _answer[0]
    monkeypatch.setattr(QMessageBox, "question", _question)

    _t._on_clear()
    assert (len(_t.value()), _t._clear.isEnabled()) == (4, True)
    _answer[0] = QMessageBox.StandardButton.Yes
    _t._on_clear()
    assert (len(_t.value()), _t._clear.isEnabled(), len(_asked)) == (0, False, 2)


# ── 붙이기 ────────────────────────────────────────────────────────────────────
def test_extend_inserts_without_reset():
    _t = _table([{"이름": "a", "수": 1}])
    _resets, _inserts, _edits = [], [], []
    _t._model.modelReset.connect(lambda: _resets.append(True))
    _t._model.rowsInserted.connect(lambda *_a: _inserts.append(tuple(_a[1:])))
    _t.edited.connect(lambda: _edits.append(True))

    _t.extend([{"이름": "b", "수": 2}, {"이름": "c", "수": 3}])

    assert (_resets, _inserts, _edits) == ([], [(1, 2)], [])
    assert _names(_t) == ["a", "b", "c"]


def test_extend_keeps_the_pick():
    """앞에 끼어도 고른 것이 그대로. 리셋이면 여기서 풀림."""
    _t = _table([{"이름": "a", "수": 5}, {"이름": "b", "수": 1}])
    _t._model.sort(1)
    _t.select(0)
    _t.extend([{"이름": "c", "수": 0}])
    assert _t.current() == 0


def test_extend_hides_what_the_filter_drops():
    _t = _table([{"이름": "a", "수": 1}])
    _t._model.filter("a")
    _t.extend([{"이름": "b", "수": 2}, {"이름": "aa", "수": 3}])
    assert (_names(_t), len(_t.value())) == (["a", "aa"], 3)


@pytest.mark.parametrize("order", [Qt.SortOrder.AscendingOrder,
                                   Qt.SortOrder.DescendingOrder])
def test_extend_under_sort_lands_where_a_rebuild_would(order):
    """같은 값끼리는 원본 순서. 안정 정렬과 같은 답이어야 다시 정렬해도 안 튐."""
    _t = _table([{"이름": _n, "수": _v} for _n, _v in [("a", 2), ("b", 1), ("c", 2)]])
    _t._model.sort(1, order)
    _t.extend([{"이름": _n, "수": _v}
               for _n, _v in [("d", 2), ("e", 0), ("f", 3), ("g", 1), ("h", None)]])

    _inserted = list(_t._model._order)
    _t._model._rebuild()
    assert _inserted == _t._model._order
