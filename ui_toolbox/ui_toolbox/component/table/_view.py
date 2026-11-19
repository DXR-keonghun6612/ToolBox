"""table 보기 - 거르기 줄 + 표. 머리글이 분명한 행 dict 목록(CSV 꼴)을 칸 선언대로. JSON 꼴 문서는 tree.

칸 선언은 config 가 줌 - 데이터가 안 듦. 머리글 글자는 칸 이름. 칸 편집은 Qt 기본 편집기, `editable` 기본 거짓.
파일을 안 읽음 - 받은 것을 쓸 꼴로 바꾸는 것은 page.

여럿 고름 - Ctrl 로 하나씩, Shift 로 구간. 고른 자리들은 `selection`, 마지막에 짚은 하나는 `current`.

`open` - 표 설정에 붙으면 고른 행이 바뀔 때 그 행 dict 를, 칸에 붙으면 그 칸을 더블클릭할 때 그 칸 값을
`open_requested(영역, 보낼 것)` 로 냄. 영역에 넘기는 것은 page.

행 위 오른쪽 클릭이 메뉴 `menu` - 항목은 소비처가 넣고 뺌, 비면 안 뜸. `export_action`(`CSV 내보내기`)도 그 항목 하나.
CSV 는 고른 행을, 고른 것이 없으면 보이는 행 전부. 누르면 칸 고르기 -> 저장 대화상자.

칸 폭 - 칸 선언의 `width` 비율로 잡고, 표 폭이 바뀌면 지금 비율대로 다시 나눔. 자투리는 마지막 칸. 사람이 끈 폭도 비율로 남음.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ._model import Table_model

__all__ = ["Table_view"]

#: 메뉴 · 대화상자 제목.
_EXPORT = "CSV 내보내기"

#: 칸 하나의 가장 작은 폭(px) - 맞출 때 칸이 사라지지 않게.
_MIN_WIDTH = 20


class _Column_pick(QDialog):
    """내보낼 칸 고르기 - 칸마다 체크, 처음엔 다 켬. 하나도 안 고르면 확인이 꺼짐."""

    def __init__(self, names: list[str], count: int, parent: QWidget) -> None:
        """Args:
        names: 후보 칸 이름 - 표 차례.
        count: 내보낼 행 수 - 제목에만.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(f"{_EXPORT} - {count} 행, 칸 고르기")
        _lay = QVBoxLayout(self)
        self._boxes = [QCheckBox(_n) for _n in names]
        for _b in self._boxes:
            _b.setChecked(True)
            _b.toggled.connect(self._sync)
            _lay.addWidget(_b)
        _row = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _row.accepted.connect(self.accept)
        _row.rejected.connect(self.reject)
        _lay.addWidget(_row)
        self._ok = _row.button(QDialogButtonBox.StandardButton.Ok)

    def names(self) -> list[str]:
        """고른 칸 이름 - 표 차례."""
        return [_b.text() for _b in self._boxes if _b.isChecked()]

    def _sync(self, *_args) -> None:
        self._ok.setEnabled(bool(self.names()))


class Table_view(QWidget):
    """CSV 꼴 행 목록 하나.

    Attributes:
        selected: 마지막에 짚은 행의 원본 자리. 고른 것이 없으면 `-1`
        double_clicked: 칸 더블클릭. `(원본 자리, 칸 이름)`. 편집 칸도 냄 - 거르는 것은 소비처
        open_requested: `(영역 이름, 보낼 것)`. 행 dict 또는 칸 값
        menu: 행 위 오른쪽 클릭 메뉴 - 소비처가 항목을 넣고 뺌
        export_action: `menu` 의 `CSV 내보내기`
    """

    selected       = Signal(int)
    double_clicked = Signal(int, str)
    open_requested = Signal(str, object)

    def __init__(self, columns: list[dict], open: str | None = None, filterable: bool = True,
                 parent: QWidget | None = None) -> None:
        """Args:
        columns: 칸 선언. 칸의 `open` 은 더블클릭에 그 칸 값을 냄.
        open: 고른 행 dict 를 보낼 영역 이름. 비면 안 냄.
        filterable: 거르기 줄을 붙이나.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._open = open
        self._model = Table_model(columns, self)

        self._view = QTreeView()
        self._view.setModel(self._model)
        self._view.setRootIsDecorated(False)            # 평평한 목록 - 펼침 표시 없음
        self._view.setUniformRowHeights(True)           # 수만 행 - 행 높이를 한 번만 잼
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        _header = self._view.header()
        _header.setSectionsClickable(True)              # 정렬은 Qt 가 아니라 model 의 사슬
        _header.sectionClicked.connect(self._on_header)
        _header.setStretchLastSection(False)            # 마지막 칸 폭은 맞추기가 정함
        self._view.viewport().installEventFilter(self)
        self._size_columns()

        self.menu = QMenu(self)
        self.export_action = self.menu.addAction(_EXPORT)
        self.export_action.triggered.connect(self._on_export)
        self.menu.aboutToShow.connect(self._sync_export)

        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        self._filter: QLineEdit | None = None
        if filterable:
            _lay.addLayout(self._build_filter())
        _lay.addWidget(self._view, stretch=1)

        self._view.selectionModel().selectionChanged.connect(self._on_selection)
        self._view.doubleClicked.connect(self._on_double)

    def _build_filter(self) -> QHBoxLayout:
        """거르기 줄 - 아무 칸이나 품으면 남김. 옆의 `초기화` 가 거르기와 정렬을 풂."""
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

    # ── 데이터 ────────────────────────────────────────────────────────────────
    def set_rows(self, rows: list[dict]) -> None:
        """행 전체를 갈아끼움. 신호 안 냄."""
        self._model.set_rows(rows)

    def extend(self, rows: list[dict]) -> None:
        """행을 끝에 붙임. 리셋이 없어 고른 자리가 안 풀림. 신호 안 냄."""
        self._model.extend(rows)

    def rows(self) -> list[dict]:
        """원본 순서의 행들 (사본)."""
        return self._model.rows()

    def reset(self) -> None:
        """거르기와 정렬을 풀어 원본 순서로."""
        if self._filter is not None:
            self._filter.clear()                    # textChanged 가 model 의 거르기를 비움
        self._model.sort(-1)

    def regions(self) -> set[str]:
        """`open_requested` 가 낼 수 있는 영역 이름 - 표의 `open`, 칸의 `open`."""
        _out = {_c["open"] for _c in self._model.columns() if _c["open"] is not None}
        if self._open is not None:
            _out.add(self._open)
        return _out

    # ── 고름 ──────────────────────────────────────────────────────────────────
    def current(self) -> int:
        """마지막에 짚은 행의 원본 자리. 없으면 `-1`. 여럿을 골라도 하나."""
        _index = self._view.currentIndex()
        return self._model.source(_index.row()) if _index.isValid() else -1

    def selection(self) -> list[int]:
        """고른 행들의 원본 자리. 보이는 순서. 없으면 빈 목록."""
        _shown = sorted({_i.row() for _i in self._view.selectionModel().selectedRows()})
        return [self._model.source(_r) for _r in _shown]

    def shown_rows(self) -> list[int]:
        """보이는 행 전부의 원본 자리. 거르기 · 정렬이 걸린 그대로."""
        return [self._model.source(_r) for _r in range(self._model.rowCount())]

    def select(self, at: int) -> None:
        """그 원본 자리의 행을 고름. 앞서 고른 것은 풀림. 안 보이는 행이면 그대로."""
        _shown = self._model.shown(at)
        if _shown >= 0:
            self._view.setCurrentIndex(self._model.index(_shown, 0))

    # ── 사람의 조작 ───────────────────────────────────────────────────────────
    def _on_header(self, section: int) -> None:
        """머리글 클릭. Shift 면 다른 칸의 정렬을 둠."""
        _shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        self._model.cycle(section, keep=bool(_shift))

    def _on_selection(self, *_args) -> None:
        _at = self.current()
        self.selected.emit(_at)
        if self._open is not None and _at >= 0:
            self.open_requested.emit(self._open, self._model.row(_at))

    def _on_double(self, index: QModelIndex) -> None:
        _at = self._model.source(index.row())
        _col = self._model.columns()[index.column()]
        self.double_clicked.emit(_at, _col["name"])
        if _col["open"] is not None:
            self.open_requested.emit(_col["open"], self._model.row(_at).get(_col["name"]))

    # ── 칸 폭 ─────────────────────────────────────────────────────────────────
    def _size_columns(self) -> None:
        """칸 선언의 `width` 를 비율로 둠. 폭이 없는 칸은 선언된 폭의 평균, 아무도 없으면 같은 폭. 첫 맞춤에서 씀."""
        _cols = self._model.columns()
        _given = [_c["width"] for _c in _cols if _c["width"] is not None]
        _mean = sum(_given) / len(_given) if _given else 1
        self._weights: list[float] | None = [_c["width"] if _c["width"] is not None else _mean for _c in _cols]
        self._fit_columns()

    def _fit_columns(self) -> None:
        """칸 폭의 합이 표 폭이 되게 비율대로 나눔 - 처음엔 선언 비율, 그 뒤엔 지금 폭. 자투리는 마지막 칸."""
        _count = self._model.columnCount()
        _total = self._view.viewport().width()
        _now = self._weights if self._weights is not None else [self._view.columnWidth(_c) for _c in range(_count)]
        if _count == 0 or _total <= 0 or sum(_now) <= 0:
            return
        self._weights = None                            # 선언 비율은 한 번 - 사람이 끈 폭을 지킴
        _scale = _total / sum(_now)
        _used = 0
        for _c in range(_count - 1):
            _w = max(_MIN_WIDTH, round(_now[_c] * _scale))
            self._view.setColumnWidth(_c, _w)
            _used += _w
        self._view.setColumnWidth(_count - 1, max(_MIN_WIDTH, _total - _used))

    def eventFilter(self, watched, event) -> bool:
        if watched is self._view.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_columns()
        return super().eventFilter(watched, event)

    # ── 메뉴, CSV ─────────────────────────────────────────────────────────────
    def contextMenuEvent(self, event) -> None:
        """표 위 오른쪽 클릭 - `menu`. 거르기 줄 위, 항목이 없으면 안 뜸."""
        if not self._view.geometry().contains(event.pos()) or not self.menu.actions():
            return
        self.menu.exec(event.globalPos())

    def _export_rows(self) -> tuple[list[int], bool]:
        """내보낼 행의 원본 자리, 고른 것인가. 고른 것이 없으면 보이는 행 전부."""
        _picked = self.selection()
        return (_picked, True) if _picked else (self.shown_rows(), False)

    def _sync_export(self) -> None:
        """메뉴가 뜨기 전 - `CSV 내보내기` 의 글자와 켜짐을 지금 행 수에."""
        _at, _picked = self._export_rows()
        self.export_action.setText(f"{_EXPORT} - {'고른' if _picked else '보이는'} {len(_at)} 행")
        self.export_action.setEnabled(bool(_at))

    def write_csv(self, path: str | Path, at: list[int] | None = None, columns: list[str] | None = None) -> int:
        """원본 자리 `at` 의 행을 csv 로 쓰고 쓴 행 수를 냄. 안 주면 보이는 행 전부.

        `columns` 는 쓸 칸 이름 - 표 차례로 씀. 안 주면 칸 전부.
        머리글은 칸 이름, 값은 표에 보이는 글자 - 사람이 본 것과 같은 파일.
        엑셀이 한글을 바로 읽게 BOM 을 붙임(`utf-8-sig`).

        Raises:
            KeyError: 없는 칸 이름일 때.
            OSError: 못 씀.
        """
        _at = self.shown_rows() if at is None else at
        _titles = self._model.titles()
        _lost = sorted(set(columns or []) - set(_titles))
        if _lost:
            raise KeyError(f"unknown columns {_lost} - have {_titles}")
        _keep = [_i for _i, _t in enumerate(_titles) if columns is None or _t in columns]
        with open(path, "w", newline="", encoding="utf-8-sig") as _f:
            _out = csv.writer(_f)
            _out.writerow([_titles[_i] for _i in _keep])
            for _row in _at:
                _line = self._model.line(_row)
                _out.writerow([_line[_i] for _i in _keep])
        return len(_at)

    def _on_export(self) -> None:
        """칸 고르기 -> 저장 대화상자 -> csv. 행은 거르기 · 정렬이 걸린 그대로."""
        _at, _ = self._export_rows()
        _pick = _Column_pick(self._model.titles(), len(_at), self)
        if not _pick.exec():
            return
        _path, _ = QFileDialog.getSaveFileName(self, _EXPORT, "table.csv", "CSV (*.csv)")
        if not _path:
            return
        try:
            self.write_csv(_path, _at, _pick.names())
        except OSError as _e:
            QMessageBox.warning(self, _EXPORT, f"못 썼습니다.\n\n{_e}")
