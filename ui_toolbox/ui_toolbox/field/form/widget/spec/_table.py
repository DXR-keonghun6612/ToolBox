"""table 표현 - 항목들을 모델 하나로 밈.

[`_stack`](../../layout/_stack.py) 과 같은 계약을 내되 항목마다 위젯을 만들지 않음.
칸이 고정된 목록이 여기 옴.

정렬과 필터링은 `보이는 순서`만 바꿈 - 원본 순서는 그대로.

정렬은 칸의 사슬. 머리글 클릭이 그 칸을 `없음 -> 오름 -> 내림 -> 없음` 으로 돌림 - 다른 칸의
정렬은 풀림. Shift+클릭은 다른 칸을 둔 채 사슬에 더함. 머리글이 `▲` · `▼` 를 달고, 사슬이
둘 이상이면 자리 번호까지.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .....style import Now
from ...._field import Order, Rows
from ...._item import Button
from ...._value import Value
from ._bar import Button_bar

_ROOT = QModelIndex()   # 평평한 표라 부모 인덱스는 늘 이것 하나

_MOVE_BUTTONS = [Button("▲", "위로", value=-1), Button("▼", "아래로", value=+1)]


class _Model(QAbstractTableModel):
    """[`Rows`](../../_field.py) 를 칸 선언대로 비추는 모델.

    `_order` 가 `보이는 자리 -> 원본 자리`. 정렬 · 필터링은 이것만 바꿈.
    `_sort` 가 `(칸, 내림인가)` 의 사슬. 앞이 우선. 비면 원본 순서.
    """

    def __init__(self, data: Rows, parent=None) -> None:
        super().__init__(parent)
        self._data = data
        self._filter = ""
        self._sort: list[tuple[int, bool]] = []
        self._order: list[int] = list(range(len(data)))

    # ── 보이는 순서 ───────────────────────────────────────────────────────────
    def source(self, at: int) -> int:
        """보이는 자리 -> 원본 자리 (범위 밖이면 `-1`)."""
        return self._order[at] if 0 <= at < len(self._order) else -1

    def shown(self, at: int) -> int:
        """원본 자리 -> 보이는 자리 (안 보이면 `-1`)."""
        return self._order.index(at) if at in self._order else -1

    def _rebuild(self) -> None:
        """필터링하고 정렬해 보이는 순서를 다시 만듦.

        사슬의 뒤 칸부터 안정 정렬 - 앞 칸이 같은 행은 뒤 칸 순서로, 다 같으면 원본 순서.
        """
        self.beginResetModel()
        self._order = [_at for _at in range(len(self._data))
                       if self._data.matches(_at, self._filter)]
        for _col, _desc in reversed(self._sort):
            _name = self._data.fields[_col].name
            self._order.sort(key=lambda _at: Order(self._data.get(_at, _name)),
                             reverse=_desc)
        self.endResetModel()

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

    # ── 계약 ──────────────────────────────────────────────────────────────────
    def rowCount(self, parent=_ROOT) -> int:
        return 0 if parent.isValid() else len(self._order)

    def columnCount(self, parent=_ROOT) -> int:
        return 0 if parent.isValid() else len(self._data.fields)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation != Qt.Orientation.Horizontal:
            return section + 1                  # 세로 머리글이 곧 순서 번호
        _title = self._data.fields[section].title()
        _rank = next((_i for _i, (_c, _) in enumerate(self._sort) if _c == section), -1)
        if _rank < 0:
            return _title
        _arrow = "▼" if self._sort[_rank][1] else "▲"
        _order = "" if len(self._sort) == 1 else str(_rank + 1)   # 번호는 사슬일 때만
        return f"{_title} {_arrow}{_order}"

    def flags(self, index: QModelIndex):
        _f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            return _f
        _field = self._data.fields[index.column()]
        if not _field.editable:
            return _f
        if _field.type is not bool:
            return _f | Qt.ItemFlag.ItemIsEditable
        # 참거짓 칸은 체크. 값이 None 이면 그 행엔 해당 없음이라 체크가 안 섬
        if self._data.get(self.source(index.row()), _field.name) is None:
            return _f
        return _f | Qt.ItemFlag.ItemIsUserCheckable

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        _field = self._data.fields[index.column()]
        _value = self._data.get(self.source(index.row()), _field.name)
        if _field.type is bool:
            if role != Qt.ItemDataRole.CheckStateRole or _value is None:
                return None
            return Qt.CheckState.Checked if _value else Qt.CheckState.Unchecked
        if role == Qt.DisplayRole:
            return _field.text(_value)
        if role == Qt.EditRole:
            return "" if _value is None else str(_value)   # 고칠 때는 값 그대로
        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        _field = self._data.fields[index.column()]
        if _field.type is bool:
            if role != Qt.ItemDataRole.CheckStateRole:
                return False
            value = Qt.CheckState(value) == Qt.CheckState.Checked
        elif role != Qt.EditRole:
            return False
        if not self._data.set(self.source(index.row()), _field.name, value):
            return False
        self.dataChanged.emit(index, index)
        return True

    # ── 뽑기 ──────────────────────────────────────────────────────────────────
    def titles(self) -> list[str]:
        """칸 머리글. 정렬 표시(`▲` · `▼`)는 빼고 선언의 이름만 - 내보낸 파일에 화살표가 남지 않게."""
        return [_c.title() for _c in self._data.fields]

    def line(self, at: int) -> list[str]:
        """원본 자리 `at` 의 한 줄. 표에 보이는 글자 그대로 - 사람이 본 것과 같게."""
        return [_c.text(self._data.get(at, _c.name)) for _c in self._data.fields]

    # ── 수명 ──────────────────────────────────────────────────────────────────
    def rows(self) -> list[dict]:
        """원본 행들 (사본)."""
        return self._data.rows()

    def move(self, at: int, step: int) -> int:
        """그 원본 자리의 행을 옮기고 새 자리를 냄."""
        _to = self._data.move(at, step)
        self._rebuild()
        return _to

    def replace(self, rows: list[dict] | None) -> None:
        """행 전체를 갈아끼움."""
        self._data.replace(rows)
        self._rebuild()

    def rebind(self, data: Rows) -> None:
        """칸 선언까지 통째로 갈아끼움."""
        self._data = data
        self._set_sort([])

    def extend(self, rows: list[dict]) -> None:
        """행을 끝에 붙임. 리셋 없이 끼워 고른 자리가 안 풀림.

        필터링에 안 걸리는 행은 안 보임. 정렬이 서 있으면 그 자리로 하나씩 끼움.
        """
        _first = len(self._data)
        for _row in rows:
            self._data.append(_row)
        _new = [_at for _at in range(_first, len(self._data))
                if self._data.matches(_at, self._filter)]
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

    def _place(self, at: int) -> int:
        """정렬이 설 때 원본 자리 `at` 이 들어갈 보이는 자리.

        같은 값끼리는 원본 순서 - `_rebuild` 의 안정 정렬과 같은 답. 붙인 행이라 그 뒤.
        """
        _lo, _hi = 0, len(self._order)
        while _lo < _hi:
            _mid = (_lo + _hi) // 2
            if self._before(self._order[_mid], at, or_same=True):
                _lo = _mid + 1
            else:
                _hi = _mid
        return _lo

    def _before(self, a: int, b: int, or_same: bool) -> bool:
        """사슬 순으로 원본 `a` 가 `b` 앞인가. 다 같으면 `or_same`."""
        for _col, _desc in self._sort:
            _name = self._data.fields[_col].name
            _ka, _kb = Order(self._data.get(a, _name)), Order(self._data.get(b, _name))
            if _ka != _kb:
                return (_ka > _kb) if _desc else (_ka < _kb)
        return or_same


class Table_view(Value):
    """칸이 고정된 항목 목록 - 필터링 줄 + 표 + 조작 줄. payload 는 `list[dict]`.

    행을 늘리고 줄이는 버튼 셋(추가 · 선택 삭제 · 목록 초기화)은 행을 안 건드리고 신호만 냄 -
    행의 원본이 어디인지는 소비처가 앎. 소비처가 원본을 고치고 `set_value` 로 되비춤.

    여럿 고름 - Ctrl 로 하나씩, Shift 로 구간. 고른 자리들은 `selection`, 마지막에 짚은 하나는
    `current`. 신호 `selected` 와 `remove_requested` 는 `current` 하나를 냄.

    행 위 오른쪽 클릭이 팝업 메뉴. 이 위젯은 `CSV 내보내기` 하나를 냄 - 고른 행을 파일로,
    고른 것이 없으면 보이는 행 전부(필터링 · 정렬이 걸린 그대로). 파생은 `fill_menu` 로 제 항목을
    더하고, 더한 것이 있으면 사이에 줄이 그어짐.

    Attributes:
        value_changed: 항목 전체
        selected: 마지막에 짚은 항목의 원본 자리. 고른 것이 없으면 `-1`
        add_requested: `추가` 눌림
        remove_requested: `선택 삭제` 눌림. 마지막에 짚은 항목의 원본 자리 하나
        clear_requested: `목록 초기화` 눌림. 묻고 Yes 일 때만
    """

    value_changed   = Signal(list)
    selected        = Signal(int)
    add_requested   = Signal()
    remove_requested = Signal(int)
    clear_requested = Signal()

    def __init__(self, data: Rows, editable: bool = False,
                 movable: bool = False, filterable: bool = True,
                 parent: QWidget | None = None) -> None:
        """표를 구성.

        Args:
            data: 비출 항목들. 칸 편집과 이동은 이 위젯이 제자리에서 고침.
            editable: 행을 늘리고 줄이는 버튼 셋을 붙이나. 칸 편집은 `Field.editable` 이 따로.
            movable: `▲▼` 를 붙이나.
            filterable: 필터링 줄을 붙이나.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._model = _Model(data, self)

        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # 여럿 고름 - Ctrl 로 하나씩, Shift 로 구간. `current` 는 그 중 마지막에 짚은 행이라
        # 행 하나를 따르는 소비처(`selected`)는 그대로 섬
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.verticalHeader().setVisible(True)    # 순서 번호
        _header = self._view.horizontalHeader()
        _header.setSectionsClickable(True)              # 정렬은 Qt 가 아니라 모델의 사슬
        _header.sectionClicked.connect(self._on_header)
        _header.setStretchLastSection(True)             # 사람이 칸을 끌어도 오른쪽에 빈틈 없음
        self._view.viewport().installEventFilter(self)  # 표 폭이 바뀌면 칸 폭을 다시 나눔
        self._size_columns(data)

        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["tight"])
        self._filter: QLineEdit | None = None
        if filterable:
            _lay.addLayout(self._build_filter())
        _lay.addWidget(self._view, stretch=1)
        _lay.addLayout(self._build_bar(editable, movable))

        self._model.dataChanged.connect(lambda *_: self._emit())
        self._view.selectionModel().selectionChanged.connect(self._on_selection)

    def _build_filter(self) -> QHBoxLayout:
        """필터링 줄 - 아무 칸이나 품으면 남김. 옆의 `초기화` 가 필터링과 정렬을 풀음.

        입력창이 표 폭을 따라감 - 줄의 남는 폭을 다 가짐.
        """
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("필터링 (* 여러 자, ? 한 자)")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._model.filter)
        _reset = QPushButton("초기화")
        _reset.setToolTip("필터링과 정렬을 풀어 원본 순서로")
        _reset.clicked.connect(self.reset)
        _row = QHBoxLayout()
        _row.setContentsMargins(0, 0, 0, 0)
        _row.addWidget(self._filter, stretch=1)
        _row.addWidget(_reset)
        return _row

    def _build_bar(self, editable: bool, movable: bool) -> QHBoxLayout:
        """표 아래 조작 줄. 고른 항목에 걸리는 버튼은 고른 것이 없으면 꺼 둠."""
        _bar = QHBoxLayout()
        _bar.setContentsMargins(0, 0, 0, 0)
        if editable:
            _add = QPushButton("추가")
            _add.clicked.connect(self.add_requested)
            _bar.addWidget(_add)
        _bar.addStretch(1)
        self._move: Button_bar | None = None
        if movable:
            self._move = Button_bar(_MOVE_BUTTONS)
            self._move.fired.connect(self._on_move)
            _bar.addWidget(self._move)
        self._remove: QPushButton | None = None
        self._clear: QPushButton | None = None
        if editable:
            self._remove = QPushButton("선택 삭제")
            self._remove.clicked.connect(lambda: self.remove_requested.emit(self.current()))
            _bar.addWidget(self._remove)
            self._clear = QPushButton("목록 초기화")
            self._clear.clicked.connect(self._on_clear)
            _bar.addWidget(self._clear)
        self._arm(-1)
        return _bar

    # ── public API ────────────────────────────────────────────────────────────
    def value(self) -> list[dict]:
        """원본 순서의 항목들."""
        return self._model.rows()

    def set_value(self, value) -> None:
        self._model.replace(value)
        self._arm(self.current())

    def extend(self, rows: list[dict]) -> None:
        """행을 끝에 붙임. 신호 안 냄 - `set_value` 와 같은 복원 쪽.

        통째로 갈 때는 `set_value`, 몇 행 늘 때는 이것. 리셋이 없어 고른 자리가 안 풀림.
        """
        self._model.extend(rows)
        self._arm(self.current())

    def _emit(self) -> None:
        """사람이 고쳤을 때의 후처리."""
        self.value_changed.emit(self.value())
        self.edited.emit()

    def set_rows(self, data: Rows) -> None:
        """칸 선언까지 갈아끼움. 칸 폭도 정렬도 다시 잡음."""
        self._model.rebind(data)
        self._size_columns(data)
        self._arm(self.current())

    def reset(self) -> None:
        """필터링과 정렬을 풀어 원본 순서로."""
        if self._filter is not None:
            self._filter.clear()                    # textChanged 가 모델의 필터를 비움
        self._model.sort(-1)

    def current(self) -> int:
        """마지막에 짚은 항목의 원본 자리. 없으면 `-1`. 여럿을 골라도 하나."""
        _index = self._view.currentIndex()
        return self._model.source(_index.row()) if _index.isValid() else -1

    def selection(self) -> list[int]:
        """고른 항목들의 원본 자리. 보이는 순서 - 정렬을 걸었으면 그 순서. 없으면 빈 목록."""
        _shown = sorted({_i.row() for _i in self._view.selectionModel().selectedRows()})
        return [self._model.source(_r) for _r in _shown]

    def shown_rows(self) -> list[int]:
        """보이는 항목 전부의 원본 자리. 필터링 · 정렬이 걸린 그대로.

        `value()` 는 원본 순서라 정렬이 안 실림. 사람이 본 차례가 필요하면 이것
        """
        return [self._model.source(_r) for _r in range(self._model.rowCount())]

    def select(self, at: int) -> None:
        """그 원본 자리의 항목을 고름. 앞서 고른 것은 풀림."""
        _shown = self._model.shown(at)
        if _shown >= 0:
            self._view.selectRow(_shown)

    # ── 내부 ──────────────────────────────────────────────────────────────────
    def _size_columns(self, data: Rows) -> None:
        """칸 선언의 `width` 를 비율로 폭을 잡음. 폭이 없는 칸은 선언된 폭의 평균."""
        _given = [_col.width for _col in data.fields if _col.width]
        _mean = sum(_given) // len(_given) if _given else 1
        for _at, _col in enumerate(data.fields):
            self._view.setColumnWidth(_at, _col.width or _mean)
        self._fit_columns()

    def _fit_columns(self) -> None:
        """칸 폭의 합이 표 폭이 되게 지금 비율대로 다시 나눔. 자투리는 마지막 칸."""
        _count = self._model.columnCount()
        _total = self._view.viewport().width()
        _now = [self._view.columnWidth(_c) for _c in range(_count)]
        if _count == 0 or _total <= 0 or sum(_now) <= 0:
            return
        _scale = _total / sum(_now)
        _used = 0
        for _c in range(_count - 1):
            _w = round(_now[_c] * _scale)
            self._view.setColumnWidth(_c, _w)
            _used += _w
        self._view.setColumnWidth(_count - 1, _total - _used)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._view.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_columns()
        return super().eventFilter(watched, event)

    def _arm(self, at: int) -> None:
        """고른 자리에 맞춰 조작 버튼을 켜고 끔."""
        _has = at >= 0
        _count = len(self._model.rows())
        if self._remove is not None:
            self._remove.setEnabled(_has)
        if self._clear is not None:
            self._clear.setEnabled(_count > 0)
        if self._move is not None:
            self._move.arm(0, _has and at > 0)
            self._move.arm(1, _has and at < _count - 1)

    def _on_header(self, section: int) -> None:
        """머리글 클릭. Shift 면 다른 칸의 정렬을 둠."""
        _shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        self._model.cycle(section, keep=bool(_shift))

    def _on_selection(self, *_args) -> None:
        _at = self.current()
        self._arm(_at)
        self.selected.emit(_at)

    def _on_clear(self) -> None:
        """목록 초기화. 되돌릴 수 없어 묻고 신호."""
        _count = len(self._model.rows())
        _answer = QMessageBox.question(self, "목록 초기화",
                                       f"항목 {_count} 개를 전부 지웁니다. 되돌릴 수 없습니다.")
        if _answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()

    def _on_move(self, step: int) -> None:
        _at = self.current()
        _to = self._model.move(_at, step)
        if _to != _at:
            self.select(_to)
            self._emit()

    # ── 팝업 메뉴 ─────────────────────────────────────────────────────────────
    def contextMenuEvent(self, event) -> None:
        """표 위 오른쪽 클릭. 이 위젯의 항목 뒤에 줄을 긋고 파생이 더한 것을 붙임.

        필터링 줄 · 조작 줄 위에서는 안 뜸 - 행에 거는 것이라
        """
        if not self._view.geometry().contains(event.pos()):
            return
        _menu = QMenu(self)
        self._base_menu(_menu)
        _at = len(_menu.actions())
        self.fill_menu(_menu)
        if len(_menu.actions()) > _at > 0:
            _menu.insertSeparator(_menu.actions()[_at])   # 더한 것이 있을 때만 줄
        if _menu.actions():
            _menu.exec(event.globalPos())

    def _base_menu(self, menu: QMenu) -> None:
        """이 위젯이 늘 내는 항목. 파생은 이것을 안 건드리고 `fill_menu` 로 더함."""
        _picked = self.selection()
        _count = len(_picked) or len(self.shown_rows())
        _act = menu.addAction(f"CSV 내보내기 - {'고른' if _picked else '보이는'} {_count} 행")
        _act.setEnabled(_count > 0)
        _act.triggered.connect(self._on_export)

    def fill_menu(self, menu: QMenu) -> None:
        """파생이 자기 항목을 더하는 자리. 기본은 아무것도 안 함.

        더한 것이 있으면 이 위젯의 항목과 사이에 줄이 그어짐. 고른 자리는 `selection` ·
        `current` 로 물을 것
        """

    # ── 내보내기 ──────────────────────────────────────────────────────────────
    def write_csv(self, path: str | Path, at: list[int] | None = None) -> int:
        """원본 자리 `at` 의 행을 csv 로 쓰고 쓴 행 수를 냄. 안 주면 보이는 행 전부.

        머리글은 칸 선언의 이름, 값은 표에 보이는 글자 - 사람이 본 것과 같은 파일.
        엑셀이 한글을 바로 읽게 BOM 을 붙임 (`utf-8-sig`)

        Raises:
            OSError: 못 씀
        """
        _at = self.shown_rows() if at is None else at
        with open(path, "w", newline="", encoding="utf-8-sig") as _f:
            _out = csv.writer(_f)
            _out.writerow(self._model.titles())
            _out.writerows(self._model.line(_row) for _row in _at)
        return len(_at)

    def _on_export(self) -> None:
        """고른 행을 csv 로. 고른 것이 없으면 보이는 행 전부 - 필터링 · 정렬이 걸린 그대로."""
        _at = self.selection() or self.shown_rows()
        if not _at:
            QMessageBox.information(self, "CSV 내보내기", "내보낼 행이 없습니다.")
            return
        _path, _ = QFileDialog.getSaveFileName(self, "CSV 내보내기", "table.csv", "CSV (*.csv)")
        if not _path:
            return
        try:
            self.write_csv(_path, _at)
        except OSError as _e:
            QMessageBox.warning(self, "CSV 내보내기", f"못 썼습니다.\n\n{_e}")
