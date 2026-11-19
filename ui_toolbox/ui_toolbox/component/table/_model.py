"""table model - 행 dict 목록을 칸 선언대로 비춤.

정렬과 거르기는 보이는 순서만 바꿈 - 원본 순서는 그대로.

정렬은 칸의 사슬. 머리글 클릭이 그 칸을 `없음 -> 오름 -> 내림 -> 없음` 으로 돌림 - 다른 칸의
정렬은 풀림. Shift+클릭은 다른 칸을 둔 채 사슬에 더함. 빈 값은 방향과 상관없이 늘 뒤.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ._column import Blank, Check_columns, Check_value, Order, Text

__all__ = ["Pattern", "Table_model"]

_ROOT = QModelIndex()   # 평평한 표라 부모 인덱스는 늘 이것 하나


@lru_cache(maxsize=8)
def Pattern(text: str) -> re.Pattern:
    """거르기 글자 -> 정규식. 부분 일치, 대소문자 무시. `*` 는 0 자 이상, `?` 는 한 자.

    행마다 다시 짓지 않게 캐시 - 한 번 거를 때 행 수만큼 불림.
    """
    _src = re.escape(text).replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(_src, re.IGNORECASE | re.DOTALL)


class Table_model(QAbstractTableModel):
    """행 dict 목록을 칸 선언대로 비추는 model.

    행 dict 는 통째로 듦 - 칸 선언에 없는 키는 안 보일 뿐.
    `_order` 가 `보이는 자리 -> 원본 자리`. 정렬 · 거르기는 이것만 바꿈.
    `_sort` 가 `(칸, 내림인가)` 의 사슬. 앞이 우선. 비면 원본 순서.
    """

    def __init__(self, columns: list[dict], parent=None) -> None:
        """Args:
        columns: 칸 선언. `Check_columns` 가 검사.
        parent: 부모 객체.
        """
        super().__init__(parent)
        self._columns = Check_columns(columns)
        self._rows: list[dict] = []
        self._filter = ""
        self._sort: list[tuple[int, bool]] = []
        self._order: list[int] = []

    # ── 행 ────────────────────────────────────────────────────────────────────
    def _check(self, row: dict) -> dict:
        """칸 선언에 있는 키의 값을 검사한 사본."""
        for _col in self._columns:
            Check_value(_col, row.get(_col["name"]))
        return dict(row)

    def columns(self) -> list[dict]:
        """칸 선언 (빠진 선택 키를 채운 것)."""
        return [dict(_c) for _c in self._columns]

    def rows(self) -> list[dict]:
        """원본 행들, 원본 순서 (사본)."""
        return [dict(_r) for _r in self._rows]

    def row(self, at: int) -> dict:
        """원본 자리 `at` 의 행 (사본)."""
        return dict(self._rows[at])

    def set_rows(self, rows: list[dict]) -> None:
        """행 전체를 갈아끼움. 정렬 · 거르기는 둠."""
        _checked = [self._check(_r) for _r in rows]
        self._rows = _checked
        self._rebuild()

    def extend(self, rows: list[dict]) -> None:
        """행을 끝에 붙임. 리셋 없이 끼워 고른 자리가 안 풀림.

        거르기에 안 걸리는 행은 안 보임. 정렬이 서 있으면 그 자리로 하나씩 끼움.
        """
        _first = len(self._rows)
        self._rows += [self._check(_r) for _r in rows]
        _new = [_at for _at in range(_first, len(self._rows)) if self._matches(_at)]
        if not _new:
            return
        if not self._sort:
            _end = len(self._order)
            self.beginInsertRows(_ROOT, _end, _end + len(_new) - 1)
            self._order += _new
            self.endInsertRows()
            return
        for _at in _new:
            _to = self._place(_at)
            self.beginInsertRows(_ROOT, _to, _to)
            self._order.insert(_to, _at)
            self.endInsertRows()

    # ── 보이는 순서 ───────────────────────────────────────────────────────────
    def source(self, at: int) -> int:
        """보이는 자리 -> 원본 자리 (범위 밖이면 `-1`)."""
        return self._order[at] if 0 <= at < len(self._order) else -1

    def shown(self, at: int) -> int:
        """원본 자리 -> 보이는 자리 (안 보이면 `-1`)."""
        return self._order.index(at) if at in self._order else -1

    def _value(self, at: int, column: int) -> Any:
        return self._rows[at].get(self._columns[column]["name"])

    def _matches(self, at: int) -> bool:
        """원본 자리 `at` 의 보이는 글자 어딘가에 거르기 글자가 있나. 칸 선언에 없는 키는 안 봄."""
        if not self._filter:
            return True
        _pat = Pattern(self._filter)
        return any(_pat.search(Text(_c, self._rows[at].get(_c["name"]))) for _c in self._columns)

    def _rebuild(self) -> None:
        """거르고 정렬해 보이는 순서를 다시 만듦.

        사슬의 뒤 칸부터 안정 정렬 - 앞 칸이 같은 행은 뒤 칸 순서로, 다 같으면 원본 순서.
        """
        self.beginResetModel()
        self._order = [_at for _at in range(len(self._rows)) if self._matches(_at)]
        for _col, _desc in reversed(self._sort):
            _c = self._columns[_col]
            # 빈 값은 방향과 상관없이 뒤 - 값 있는 것만 뒤집고 빈 것은 차례 그대로 뒤에
            _full = [_at for _at in self._order if self._value(_at, _col) is not None]
            _empty = [_at for _at in self._order if self._value(_at, _col) is None]
            _full.sort(key=lambda _at: Order(_c, self._value(_at, _col)), reverse=_desc)
            self._order = _full + _empty
        self.endResetModel()

    def _place(self, at: int) -> int:
        """정렬이 설 때 원본 자리 `at` 이 들어갈 보이는 자리.

        같은 값끼리는 원본 순서 - `_rebuild` 의 안정 정렬과 같은 답. 붙인 행이라 그 뒤.
        """
        _lo, _hi = 0, len(self._order)
        while _lo < _hi:
            _mid = (_lo + _hi) // 2
            if self._before(self._order[_mid], at):
                _lo = _mid + 1
            else:
                _hi = _mid
        return _lo

    def _before(self, a: int, b: int) -> bool:
        """사슬 순으로 원본 `a` 가 `b` 앞인가 (같으면 참). 빈 값은 방향과 상관없이 뒤."""
        for _col, _desc in self._sort:
            _c = self._columns[_col]
            _va, _vb = self._value(a, _col), self._value(b, _col)
            if (_va is None) != (_vb is None):
                return _vb is None
            _ka, _kb = Order(_c, _va), Order(_c, _vb)
            if _ka != _kb:
                return (_ka > _kb) if _desc else (_ka < _kb)
        return True

    def filter(self, text: str) -> None:
        """그 글자를 품은 행만 보임. `*` 는 0 자 이상, `?` 는 한 자."""
        self._filter = text
        self._rebuild()

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        """그 칸 하나로 정렬. 다른 칸의 정렬은 풀림.

        Args:
            column: 정렬 기준 칸. 음수면 원본 순서.
            order: 오름차순인가 내림차순인가.
        """
        self._set_sort([] if column < 0
                       else [(column, order == Qt.SortOrder.DescendingOrder)])

    def cycle(self, column: int, keep: bool = False) -> None:
        """그 칸을 `없음 -> 오름 -> 내림 -> 없음` 으로 한 단 돌림. 머리글을 누르면 옴.

        Args:
            column: 돌릴 칸.
            keep: 다른 칸의 정렬을 두나. 두면 그 칸이 사슬 뒤에 붙음.
        """
        _was = next((_d for _c, _d in self._sort if _c == column), None)   # None = 없음
        _next = {None: False, False: True, True: None}[_was]
        _chain = [_x for _x in self._sort if _x[0] != column] if keep else []
        if _next is not None:
            # 이미 사슬에 있던 칸은 그 자리를 지킴. 새 칸은 뒤에
            _at = next((_i for _i, (_c, _) in enumerate(self._sort) if _c == column), len(_chain))
            _chain.insert(min(_at, len(_chain)), (column, _next))
        self._set_sort(_chain)

    def _set_sort(self, chain: list[tuple[int, bool]]) -> None:
        self._sort = chain
        self._rebuild()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)

    # ── Qt model 계약 ─────────────────────────────────────────────────────────
    def rowCount(self, parent=_ROOT) -> int:
        return 0 if parent.isValid() else len(self._order)

    def columnCount(self, parent=_ROOT) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        _name = self._columns[section]["name"]
        _rank = next((_i for _i, (_c, _) in enumerate(self._sort) if _c == section), -1)
        if _rank < 0:
            return _name
        _arrow = "▼" if self._sort[_rank][1] else "▲"
        _nth = "" if len(self._sort) == 1 else str(_rank + 1)   # 번호는 사슬일 때만
        return f"{_name} {_arrow}{_nth}"

    def flags(self, index: QModelIndex):
        _f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            return _f
        _c = self._columns[index.column()]
        if _c["type"] == "bool":
            # 참거짓 칸은 체크. 값이 None 이면 그 행엔 해당 없음이라 체크가 안 섬
            if _c["editable"] and self._value(self.source(index.row()), index.column()) is not None:
                return _f | Qt.ItemFlag.ItemIsUserCheckable
            return _f
        return _f | Qt.ItemFlag.ItemIsEditable if _c["editable"] else _f

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        _c = self._columns[index.column()]
        _value = self._value(self.source(index.row()), index.column())
        if _c["type"] == "bool":
            if role != Qt.ItemDataRole.CheckStateRole or _value is None:
                return None
            return Qt.CheckState.Checked if _value else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return Text(_c, _value)
        if role == Qt.ItemDataRole.EditRole:
            # 칸 타입으로 - Qt 기본 편집기가 타입 따라 스핀 · 실수 스핀 · 한 줄 입력. float 칸의 int 도 실수 스핀
            return Blank(_c) if _value is None else type(Blank(_c))(_value)
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False
        _c = self._columns[index.column()]
        if _c["type"] == "bool":
            if role != Qt.ItemDataRole.CheckStateRole:
                return False
            value = Qt.CheckState(value) == Qt.CheckState.Checked
        elif role != Qt.ItemDataRole.EditRole:
            return False
        Check_value(_c, value)
        _row = self._rows[self.source(index.row())]
        if _row.get(_c["name"]) == value:
            return False
        _row[_c["name"]] = value
        self.dataChanged.emit(index, index)
        return True

    # ── 뽑기 ──────────────────────────────────────────────────────────────────
    def titles(self) -> list[str]:
        """칸 머리글. 정렬 표시(`▲` · `▼`)는 빼고 - 내보낸 파일에 화살표가 남지 않게."""
        return [_c["name"] for _c in self._columns]

    def line(self, at: int) -> list[str]:
        """원본 자리 `at` 의 한 줄. 표에 보이는 글자 그대로 - 사람이 본 것과 같게."""
        return [Text(_c, self._rows[at].get(_c["name"])) for _c in self._columns]
