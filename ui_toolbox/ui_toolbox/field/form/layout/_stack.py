"""layout 표현 - 항목마다 위젯 한 줄을 만들어 세로로 쌓음.

칸이 상황따라 숨거나 안에 폼이 통째로 드는 항목이 여기 옴. 칸이 고정된 목록은
[`_table`](_table.py) 이 맡음 - 항목 수만큼 위젯 트리를 만들지 않음.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....style import HEADER, Mark, Now
from ..._field import Field, Rows
from ..._item import Button
from ..._value import Value
from ..widget import Build, Button_bar

_MOVE   = [Button("▲", "위로", value=-1), Button("▼", "아래로", value=+1)]
_REMOVE = [Button("✕", "제거")]


def drop(*widgets: QWidget) -> None:
    """위젯을 부모에서 떼고 파괴를 예약한다."""
    for _w in widgets:
        _w.setParent(None)
        _w.deleteLater()


class Stack_view(Value):
    """항목 위젯을 세로로 쌓는 목록. payload 는 `list[dict]`.

    칸 위젯은 등록표가 지음. 서브클래스는 `_cell` 로 갈아끼우거나 `_extras` 로 덧붙임.

    Attributes:
        value_changed: 항목 전체
    """

    value_changed = Signal(list)

    def __init__(self, data: Rows, add_label: str = "+ 추가", title: str = "",
                 header: bool = True, movable: bool = False,
                 parent: QWidget | None = None) -> None:
        """목록을 구성.

        Args:
            data: 비출 항목들. 이 위젯이 제자리에서 고침.
            add_label: 하단 추가 버튼 라벨. 빈 문자열이면 버튼 없음.
            title: 맨 위 라벨. 빈 문자열이면 없음.
            header: 칸 머리글 줄을 붙이나. 칸이 상황따라 숨는 항목이면 끔.
            movable: 항목마다 ``▲▼`` 를 붙이나.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._data = data
        self._movable = movable
        self._rows: list[QWidget] = []

        _root = QVBoxLayout(self)
        _root.setContentsMargins(0, 0, 0, 0)
        _root.setSpacing(Now()["tight"])
        if title:
            _root.addWidget(QLabel(title))
        if header:
            _root.addWidget(_Header(data.fields))
        self._row_lay = QVBoxLayout()
        self._row_lay.setContentsMargins(0, 0, 0, 0)
        self._row_lay.setSpacing(Now()["tight"])
        _root.addLayout(self._row_lay)
        _root.addStretch(1)
        if add_label:
            _add = QPushButton(add_label)
            _add.clicked.connect(self._on_add)
            _root.addWidget(_add)
        self.refresh()

    # ── 서브클래스 훅 ─────────────────────────────────────────────────────────
    def _cell(self, at: int, column: Field) -> Value:
        """항목 `at` 의 `column` 칸 위젯. 등록표가 지음.

        Args:
            at: 항목 자리.
            column: 칸 선언.

        Returns:
            그 칸을 편집할 위젯. 사람이 고치면 `_commit` 을 부름.

        Raises:
            TypeError: 등록표에 그 칸의 자리가 없을 때.
        """
        _w = Build(column, labelled=False)   # 이름은 머리줄이 이미 듦
        if _w is None:
            raise TypeError(f"등록표에 자리가 없는 칸: {column.name}: {column.type}")
        # 그 행에 칸이 없을 때 무엇을 쓸지는 선언이 이미 듦
        _value = self._data.get(at, column.name)
        _w.set_value(column.default if _value is None else _value)
        if column.width:
            _w.setFixedWidth(column.width)
        _w.edited.connect(
            lambda _a=at, _k=column.name, _v=_w: self._commit(_a, _k, _v.value()))
        return _w

    def _extras(self, at: int) -> list[QWidget]:
        """항목 ``at`` 의 칸 뒤에 붙일 위젯들. 기본 없음."""
        return []

    # ── public API ────────────────────────────────────────────────────────────
    def value(self) -> list[dict]:
        return self._data.rows()

    def set_value(self, value) -> None:
        self._data.replace(value)
        self.refresh()

    def refresh(self) -> None:
        """항목 줄을 통째로 다시 그림. 자리 번호가 밀리므로 구조가 바뀌면 늘 이것."""
        for _row in self._rows:
            drop(_row)
        self._rows = []
        for _at in range(len(self._data)):
            _row = self._build_row(_at)
            self._rows.append(_row)
            self._row_lay.addWidget(_row)

    # ── 내부 ──────────────────────────────────────────────────────────────────
    def _build_row(self, at: int) -> QWidget:
        """항목 하나의 줄 - 칸들 + 덧위젯 + 이동 · 제거."""
        _row = QWidget()
        _lay = QHBoxLayout(_row)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["gap"])
        for _col in self._data.fields:
            _w = self._cell(at, _col)
            _lay.addWidget(_w, stretch=0 if _col.width else 1)
        for _w in self._extras(at):
            _lay.addWidget(_w)
        if self._movable:
            _move = Button_bar(_MOVE)
            _move.arm(0, at > 0)
            _move.arm(1, at < len(self._data) - 1)
            _move.fired.connect(lambda _step, _a=at: self._on_move(_a, _step))
            _lay.addWidget(_move)
        _remove = Button_bar(_REMOVE)
        _remove.fired.connect(lambda _v, _a=at: self._on_remove(_a))
        _lay.addWidget(_remove)
        return _row

    def _emit(self) -> None:
        """사람이 고쳤을 때의 후처리."""
        self.value_changed.emit(self.value())
        self.edited.emit()

    def _commit(self, at: int, key: str, value) -> None:
        """칸 값을 데이터에 적음. 실제로 바뀐 때만 알림."""
        if self._data.set(at, key, value):
            self._emit()

    def _on_add(self) -> None:
        self._data.append({})
        self.refresh()
        self._emit()

    def _on_remove(self, at: int) -> None:
        if self._data.remove(at):
            self.refresh()
            self._emit()

    def _on_move(self, at: int, step: int) -> None:
        if self._data.move(at, step) != at:
            self.refresh()
            self._emit()


class _Header(QWidget):
    """칸 머리글 한 줄. 항목이 쓰는 ``Field`` 그대로 지어 폭을 두 곳에 안 적음."""

    def __init__(self, fields: list[Field], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _style = Now()
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(_style["gap"])
        for _col in fields:
            _lbl = Mark(QLabel(_col.title()), HEADER)
            if _col.tip:
                _lbl.setToolTip(_col.tip)
            if _col.width:
                _lbl.setFixedWidth(_col.width)
                _lay.addWidget(_lbl)
            else:
                _lay.addWidget(_lbl, stretch=1)
        _lay.addSpacing(_style["button"] + _style["gap"])   # ✕ 자리
