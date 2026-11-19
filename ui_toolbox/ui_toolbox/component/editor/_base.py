"""편집기 골격과 도구 계약 - 무엇을 편집하는지, 좌표계가 몇 차원인지 모름.

- 도구는 `Tool` 선언 - 툴바 버튼, 단축키, 배타 묶음을 선언에서 지음. 쓸 도구는 생성자의 `key` 목록, 비면 보기
- 툴바, 옵션은 멤버 위젯 - 자리는 생성자 인자(`toolbar`, `options`). `None` 이면 안 놓음 - 멤버로 소비처가 놓음.
  툴바가 왼쪽 · 오른쪽이면 버튼이 세로. 위 · 아래에 둘 다면 한 줄 - 툴바, 옵션 차례
- 신호는 자료형 단위, 차원 `D` 를 가리지 않음 - 상자 `(2, D)`, 꼭짓점 `(N, D)` + 닫힘 · 반경, `picked` 좌표 `(D,)` + 토글.
  모든 신호 끝에 표시 글자 - 도구 `key` 또는 고정 이름(`pick`, `lasso`)
- 보기로 시작 - 고른 도구 없음. 툴바 맨 앞 보기 버튼(V)으로 돌아감. 도구가 없으면 보기 버튼도 없음
- 데이터, 기하 정의(bbox, polygon), 되돌리기 이력은 받는 쪽이 듦 - 편집기는 신호만
- 조준 - 대상이 바뀔 때만 진행 중 조작을 버림, 도구 선택은 둠. 대상은 영상 - 같은 영상의 객체만 바뀐 것은 바뀜 아님. 포커스가
  옮겨진 것은 아무것도 안 지움
- `setEnabled` - 편집만 막고 보기, 확대는 살림. 하나씩 고르기는 편집 아님, 여럿 묶기(Shift 토글, 올가미)는 막힘
- 보기 상태의 좌클릭 - 안 끌었으면 `picked`, 끌었으면 지나온 점이 올가미. 끌었나는 캔버스가 판정
- Esc - 진행 중 조작(올가미 포함)이 있으면 취소, 없으면 보기로
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ._tool import Tool

__all__ = ["Draw_tool", "Editor_base"]


class Draw_tool:
    """도구 하나 - 선언한 버튼들 + 포인터 상호작용 + 자기 미리보기. 실제 도구는 raster 안에서 상속.

    진행 중 상호작용 상태만 듦 - 데이터는 받는 쪽.
    """

    #: 이 도구가 선언하는 버튼들.
    TOOLS: tuple[Tool, ...] = ()

    def __init__(self, editor: Editor_base) -> None:
        """Args:
        editor: 이 도구를 든 편집기 - 신호, 캔버스를 여기서 씀.
        """
        self._e = editor

    def press(self, point: tuple[float, ...]) -> None:
        """좌클릭. `point` 는 캔버스 좌표 `(D,)`."""

    def move(self, point: tuple[float, ...]) -> None:
        """포인터 이동."""

    def release(self, point: tuple[float, ...]) -> None:
        """좌클릭 해제."""

    def right(self, point: tuple[float, ...]) -> None:
        """우클릭."""

    def clear_transient(self) -> None:
        """진행 중 조작(그리던 도형, 미리보기)을 버림."""

    def busy(self) -> bool:
        """진행 중 조작이 있나 - Esc 가 취소할지 보기로 갈지 가름."""
        return False

    def build_options(self, row: QHBoxLayout) -> None:
        """옵션 위젯을 얹음 (굵기 등). 이 도구가 고른 동안만 보임."""


class Editor_base(QWidget):
    """편집기 골격. 서브클래스(raster)가 캔버스와 도구 종류를 줌.

    Attributes:
        box: 상자 `(2, D)` - 최소 꼭짓점, 최대 꼭짓점, 표시.
        vertices: 꼭짓점 `(N, D)`, 닫힘, 반경, 표시.
        picked: 좌표 `(D,)`, 토글, 표시(`pick`) - 보기의 좌클릭. 토글은 Shift - 선택에 없으면 추가, 있으면 제외.
            무엇을 고를지, 선택이 무엇인지는 받는 쪽.
        toolbar: 도구 버튼 위젯.
        options: 지금 도구의 옵션 위젯.
    """

    #: 툴바, 옵션이 갈 수 있는 자리.
    TOOLBAR_AT = ("top", "bottom", "left", "right")
    OPTIONS_AT = ("top", "bottom")

    #: 서브클래스가 가진 도구 종류.
    TOOL_TYPES: tuple[type[Draw_tool], ...] = ()

    #: 도구 아닌 손짓의 표시.
    PICK, LASSO = "pick", "lasso"

    #: 보기 버튼 - 도구가 아님. 고른 도구를 풂.
    VIEW = Tool("view", "", "👁", "보기", "V", "고르기 - 클릭은 하나, 끌면 올가미")

    box      = Signal(object, str)
    vertices = Signal(object, bool, float, str)
    picked   = Signal(object, bool, str)

    def __init__(self, canvas: QWidget, tools: list[str], toolbar: str | None = "top",
                 options: str | None = "top", parent: QWidget | None = None) -> None:
        """Args:
        canvas: 보이는 캔버스. 포인터 신호는 서브클래스가 `_press` 등에 이음.
        tools: 쓸 도구 `key` 목록. 비면 보기.
        toolbar: 툴바 자리 - `TOOLBAR_AT` 하나, `None` 이면 안 놓음.
        options: 옵션 자리 - `OPTIONS_AT` 하나, `None` 이면 안 놓음.
        parent: 부모 위젯.

        Raises:
            ValueError: `TOOL_TYPES` 에 없는 `key` 일 때, `key` 가 겹칠 때, 모르는 자리일 때.
        """
        if toolbar is not None and toolbar not in self.TOOLBAR_AT:
            raise ValueError(f"toolbar must be one of {self.TOOLBAR_AT} or None - got {toolbar!r}")
        if options is not None and options not in self.OPTIONS_AT:
            raise ValueError(f"options must be one of {self.OPTIONS_AT} or None - got {options!r}")
        super().__init__(parent)
        self.canvas = canvas
        self._editable = True
        self._key: Any = None
        self._lasso: list[tuple[float, ...]] | None = None   # 보기에서 누른 뒤 지나온 점
        self._current: str = ""
        self._tools: dict[str, Draw_tool] = {}         # key -> 그 버튼을 선언한 도구
        self._declared: dict[str, Tool] = {}
        self._option_box: dict[int, QWidget] = {}       # 도구 id -> 옵션 묶음

        _known = {_t.key: _type for _type in self.TOOL_TYPES for _t in _type.TOOLS}
        _unknown = [_k for _k in tools if _k not in _known]
        if _unknown:
            raise ValueError(f"unknown tools {_unknown} - known {list(_known)}")
        if len(set(tools)) != len(tools):
            raise ValueError(f"duplicate tool keys - {tools}")
        _made: dict[type, Draw_tool] = {}
        for _k in tools:
            _type = _known[_k]
            if _type not in _made:                      # setdefault 는 있어도 새로 지음 - 단축키, 층이 겹침
                _made[_type] = _type(self)
            self._tools[_k] = _made[_type]
            self._declared[_k] = next(_t for _t in _type.TOOLS if _t.key == _k)

        self.toolbar = self._build_toolbar(tools, toolbar in ("left", "right"))
        self.options = self._build_options(_made.values())
        self._place(toolbar, options)
        _esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        _esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        _esc.activated.connect(self._escape)
        self._sync()

    # ── 짓기 ──────────────────────────────────────────────────────────────────
    def _place(self, toolbar: str | None, options: str | None) -> None:
        """위 줄, 가운데(왼쪽, 캔버스, 오른쪽), 아래 줄. 위 · 아래 줄은 툴바, 옵션 차례."""
        _lay = QVBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        for _side in ("top", "middle", "bottom"):
            if _side == "middle":
                _mid = QHBoxLayout()
                _mid.setContentsMargins(0, 0, 0, 0)
                if toolbar == "left":
                    _mid.addWidget(self.toolbar)
                _mid.addWidget(self.canvas, stretch=1)
                if toolbar == "right":
                    _mid.addWidget(self.toolbar)
                _lay.addLayout(_mid, stretch=1)
                continue
            _row = [_w for _w, _at in ((self.toolbar, toolbar), (self.options, options)) if _at == _side]
            if _row:
                _line = QHBoxLayout()
                _line.setContentsMargins(0, 0, 0, 0)
                for _w in _row:
                    _line.addWidget(_w)
                _lay.addLayout(_line)

    def _build_toolbar(self, tools: list[str], vertical: bool) -> QWidget:
        """선언 -> 버튼 줄. 맨 앞에 보기 버튼 - 도구가 없으면 없음.

        고른 것 하나만 눌림 - `_sync` 가 맞춤. Qt 배타 묶음은 눌린 버튼을 코드로 못 풀어 안 씀.
        """
        _bar = QWidget()
        _lay = QVBoxLayout(_bar) if vertical else QHBoxLayout(_bar)
        _lay.setContentsMargins(0, 0, 0, 0)
        self._buttons: dict[str, QToolButton] = {}
        _entries = [(self.VIEW, self.set_view)] if tools else []
        _entries += [(self._declared[_k], lambda k=_k: self.set_tool(k)) for _k in tools]
        for _t, _slot in _entries:
            _b = QToolButton()
            _b.setText(_t.icon)
            _b.setToolTip(_t.tooltip())
            _b.setCheckable(True)
            _b.clicked.connect(lambda _c=False, s=_slot: s())
            _lay.addWidget(_b)
            self._buttons[_t.key] = _b
            if _t.shortcut:
                _sc = QShortcut(QKeySequence(_t.shortcut), self)
                _sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                _sc.activated.connect(_slot)
        _lay.addStretch(1)
        return _bar

    def _build_options(self, tools) -> QWidget:
        """도구마다 옵션 묶음 하나 - 지금 도구의 것만 보임."""
        _host = QWidget()
        _lay = QHBoxLayout(_host)
        _lay.setContentsMargins(0, 0, 0, 0)
        for _tool in tools:
            _box = QWidget()
            _row = QHBoxLayout(_box)
            _row.setContentsMargins(0, 0, 0, 0)
            _tool.build_options(_row)
            _lay.addWidget(_box)
            self._option_box[id(_tool)] = _box
        _lay.addStretch(1)
        return _host

    # ── 도구 ──────────────────────────────────────────────────────────────────
    def tool(self) -> str:
        """지금 도구 `key`. 보기면 빈 글자."""
        return self._current

    def set_tool(self, key: str) -> None:
        """도구를 고름. 그리던 것은 버림 - 도구가 바뀌면 뜻을 잃음.

        Raises:
            ValueError: 쓰지 않는 도구일 때.
        """
        if key not in self._tools:
            raise ValueError(f"tool not in use {key!r} - in use {list(self._tools)}")
        self._clear()
        self._current = key
        self._sync()

    def set_view(self) -> None:
        """보기로 - 고른 도구를 풂. 그리던 것은 버림."""
        self._clear()
        self._current = ""
        self._sync()

    def _escape(self) -> None:
        """Esc - 진행 중 조작이 있으면 취소, 없으면 보기로."""
        if self._lasso is not None or any(_t.busy() for _t in set(self._tools.values())):
            self._clear()
        else:
            self.set_view()

    # ── 조준 ──────────────────────────────────────────────────────────────────
    def aim(self, key: Any) -> None:
        """편집 대상을 알림. `key` 가 바뀔 때만 진행 중 조작을 버림 - 도구 선택은 둠."""
        if key != self._key:
            self._clear()
        self._key = key

    # ── 잠금 ──────────────────────────────────────────────────────────────────
    def setEnabled(self, on: bool) -> None:
        """편집만 막고 보기, 확대는 살림 - 캔버스는 안 끔. page 의 guard 가 부름."""
        self._editable = bool(on)
        if not self._editable:
            self._clear()
        self._sync()

    def isEnabled(self) -> bool:
        return self._editable

    # ── 포인터 - 서브클래스가 캔버스 신호를 이리로 ─────────────────────────────────
    def _press(self, point: tuple[float, ...]) -> None:
        _tool = self._active()
        if _tool is not None:
            _tool.press(point)
            return
        self._lasso = [point]

    def _move(self, point: tuple[float, ...]) -> None:
        _tool = self._active()
        if _tool is not None:
            _tool.move(point)
        elif self._lasso is not None:
            self._lasso.append(point)
            if self._editable:
                self._show_lasso(self._lasso)

    def _release(self, point: tuple[float, ...], dragged: bool) -> None:
        """좌클릭 해제. `dragged` 는 캔버스가 판정 - 누른 자리에서 끌기 거리 이상 움직였나."""
        _tool = self._active()
        if _tool is not None:
            _tool.release(point)
            return
        _path, self._lasso = self._lasso, None
        self._show_lasso(None)
        if _path is None:
            return                                      # 누른 것이 없음 - Esc 로 취소됨 등
        if dragged:
            if self._editable:                          # 여럿 묶기는 편집 - 잠근 동안 막힘
                self.vertices.emit(np.asarray(_path + [point], dtype=float), True, 0.0, self.LASSO)
            return
        _toggle = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        if _toggle and not self._editable:
            return
        self.picked.emit(_path[0], _toggle, self.PICK)

    def _right(self, point: tuple[float, ...]) -> None:
        _tool = self._active()
        if _tool is not None:
            _tool.right(point)

    # ── 안 ────────────────────────────────────────────────────────────────────
    def _active(self) -> Draw_tool | None:
        """포인터를 받을 도구. 보기거나 잠겼으면 None."""
        if not self._editable or not self._current:
            return None
        return self._tools[self._current]

    def _clear(self) -> None:
        """진행 중 조작을 버림 - 도구의 것, 올가미."""
        self._lasso = None
        self._show_lasso(None)
        for _tool in set(self._tools.values()):
            _tool.clear_transient()

    def _show_lasso(self, points: list[tuple[float, ...]] | None) -> None:
        """끄는 동안 올가미 경로를 보임. None 이면 지움. 골격은 차원을 몰라 못 그림 - 서브클래스가."""

    def _sync(self) -> None:
        """버튼, 옵션, 캔버스 포인터를 지금 상태에 맞춤."""
        self.toolbar.setEnabled(self._editable)
        self.options.setEnabled(self._editable)
        for _k, _b in self._buttons.items():
            _b.setChecked(_k == (self._current or self.VIEW.key))
        _now = self._tools.get(self._current)
        for _tool in set(self._tools.values()):
            self._option_box[id(_tool)].setVisible(_tool is _now)
