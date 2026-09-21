"""table 표현 - 항목들을 모델 하나로 밈.

[`_stack`](../../layout/_stack.py) 과 같은 계약을 내되 항목마다 위젯을 만들지 않음.
칸이 고정된 목록이 여기 옴.

정렬과 필터링은 `보이는 순서`만 바꿈 - 원본 순서는 그대로.

정렬은 칸의 사슬. 머리글 클릭이 그 칸을 `없음 -> 오름 -> 내림 -> 없음` 으로 돌림 - 다른 칸의
정렬은 풀림. Shift+클릭은 다른 칸을 둔 채 사슬에 더함. 머리글이 `▲` · `▼` 를 달고, 사슬이
둘 이상이면 자리 번호까지.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .....style import LABEL, Mark, Now
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

    # ── 수명 ──────────────────────────────────────────────────────────────────
    def rows(self) -> list[dict]:
        """원본 행들 (사본)."""
        return self._data.rows()

    def append(self) -> int:
        """빈 행을 끝에 붙이고 그 원본 자리를 냄."""
        _at = self._data.append({})
        self._rebuild()
        return _at

    def remove(self, at: int) -> bool:
        """그 원본 자리의 행을 뺌."""
        if not self._data.remove(at):
            return False
        self._rebuild()
        return True

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

    Attributes:
        value_changed: 항목 전체
        selected: 고른 항목의 원본 자리. 고른 것이 없으면 `-1`
    """

    value_changed = Signal(list)
    selected      = Signal(int)

    def __init__(self, data: Rows, add_label: str = "+ 추가",
                 movable: bool = False, filterable: bool = True,
                 parent: QWidget | None = None) -> None:
        """표를 구성.

        Args:
            data: 비출 항목들. 이 위젯이 제자리에서 고침.
            add_label: 추가 버튼 라벨. 빈 문자열이면 조작 줄의 추가 · 선택 삭제 · 목록 초기화 없음.
            movable: `▲▼` 를 붙이나.
            filterable: 필터링 줄을 붙이나.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._model = _Model(data, self)

        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._view.verticalHeader().setVisible(True)    # 순서 번호
        _header = self._view.horizontalHeader()
        _header.setSectionsClickable(True)              # 정렬은 Qt 가 아니라 모델의 사슬
        _header.sectionClicked.connect(self._on_header)
        self._size_columns(data)

        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["tight"])
        self._filter: QLineEdit | None = None
        if filterable:
            _lay.addLayout(self._build_filter())
        _lay.addWidget(self._view, stretch=1)
        _lay.addLayout(self._build_bar(add_label, movable))

        self._model.dataChanged.connect(lambda *_: self._emit())
        self._view.selectionModel().selectionChanged.connect(self._on_selection)

    def _build_filter(self) -> QHBoxLayout:
        """필터링 줄 - 아무 칸이나 품으면 남김. 옆의 `초기화` 가 필터링과 정렬을 풀음."""
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("필터링 (* 여러 자, ? 한 자)")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._model.filter)
        _reset = QPushButton("초기화")
        _reset.setToolTip("필터링과 정렬을 풀어 원본 순서로")
        _reset.clicked.connect(self.reset)
        _row = QHBoxLayout()
        _row.setContentsMargins(0, 0, 0, 0)
        _row.addWidget(Mark(self._filter, LABEL))
        _row.addWidget(_reset)
        _row.addStretch(1)
        return _row

    def _build_bar(self, add_label: str, movable: bool) -> QHBoxLayout:
        """표 아래 조작 줄. 고른 항목에 걸리므로 고른 것이 없으면 꺼 둠."""
        _bar = QHBoxLayout()
        _bar.setContentsMargins(0, 0, 0, 0)
        if add_label:
            _add = QPushButton(add_label)
            _add.clicked.connect(self._on_add)
            _bar.addWidget(_add)
        _bar.addStretch(1)
        self._move: Button_bar | None = None
        if movable:
            self._move = Button_bar(_MOVE_BUTTONS)
            self._move.fired.connect(self._on_move)
            _bar.addWidget(self._move)
        self._remove: QPushButton | None = None
        self._clear: QPushButton | None = None
        if add_label:
            self._remove = QPushButton("선택 삭제")
            self._remove.clicked.connect(self._on_remove)
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
        """고른 항목의 원본 자리. 없으면 `-1`."""
        _index = self._view.currentIndex()
        return self._model.source(_index.row()) if _index.isValid() else -1

    def select(self, at: int) -> None:
        """그 원본 자리의 항목을 고름."""
        _shown = self._model.shown(at)
        if _shown >= 0:
            self._view.selectRow(_shown)

    # ── 내부 ──────────────────────────────────────────────────────────────────
    def _size_columns(self, data: Rows) -> None:
        """칸 선언대로 폭을 잡음. 폭이 없는 칸은 남는 폭을 나눠 가짐."""
        _header = self._view.horizontalHeader()
        for _at, _col in enumerate(data.fields):
            if _col.width:
                self._view.setColumnWidth(_at, _col.width)
                _header.setSectionResizeMode(_at, QHeaderView.ResizeMode.Interactive)
            else:
                _header.setSectionResizeMode(_at, QHeaderView.ResizeMode.Stretch)

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

    def _on_add(self) -> None:
        self.select(self._model.append())
        self._emit()

    def _on_remove(self) -> None:
        if self._model.remove(self.current()):
            self._arm(self.current())
            self._emit()

    def _on_clear(self) -> None:
        """행 전부 삭제. 되돌릴 수 없어 묻고 지움."""
        _count = len(self._model.rows())
        _answer = QMessageBox.question(self, "목록 초기화", f"행 {_count} 개를 전부 지웁니다.")
        if _answer != QMessageBox.StandardButton.Yes:
            return
        self._model.replace([])
        self._arm(-1)
        self._emit()

    def _on_move(self, step: int) -> None:
        _at = self.current()
        _to = self._model.move(_at, step)
        if _to != _at:
            self.select(_to)
            self._emit()
