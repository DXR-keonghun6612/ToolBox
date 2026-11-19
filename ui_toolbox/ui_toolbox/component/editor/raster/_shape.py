"""모양 도구 - 상자, 다각형. 점을 모아 도형을 만드는 일을 함께 씀.

- 상자 : 끌기. 뗄 때 `box` - 가로, 세로가 편집기의 `min_size` 보다 작으면 안 냄
- 다각형 : 클릭으로 점, 우클릭으로 마지막 점 빼기, C 나 Enter 로 닫음 - 점이 셋 이상, 둘레 상자 가로, 세로가 `min_size` 이상일 때
  `vertices`
- 미리보기 - 이중 외곽선만. 안쪽은 그대로
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from .._base import Draw_tool
from .._tool import Tool
from ._preview import Preview

__all__ = ["Shape_tool"]

#: 미리보기 층의 z.
_Z = 900.0


class Shape_tool(Draw_tool):
    """상자, 다각형."""

    TOOLS = (Tool("box", "edit", "▭", "상자", "R", "끌어서 상자"),
             Tool("polygon", "edit", "⬠", "다각형", "P", "클릭으로 점, 우클릭으로 점 빼기, C / Enter 로 닫음"))

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self._preview = Preview(editor, _Z)
        self._start: tuple[float, float] | None = None     # 상자 - 누른 자리
        self._points: list[tuple[float, float]] = []       # 다각형 - 찍은 점
        for _key in (Qt.Key.Key_C, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            _sc = QShortcut(QKeySequence(_key), editor)
            _sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            _sc.activated.connect(self._close)

    def _show(self, points: list[tuple[float, float]], closed: bool) -> None:
        """이중 외곽선."""
        self._preview.outline(points, closed)

    # ── 포인터 ────────────────────────────────────────────────────────────────
    def press(self, point) -> None:
        if self._e.tool() == "box":
            self._start = point
        else:
            self._points.append(point)
            self._show_polygon(point)

    def move(self, point) -> None:
        if self._e.tool() == "box":
            if self._start is not None:
                (_x0, _y0), (_x1, _y1) = self._start, point
                self._show([(_x0, _y0), (_x1, _y0), (_x1, _y1), (_x0, _y1)], closed=True)
        elif self._points:
            self._show_polygon(point)

    def release(self, point) -> None:
        if self._e.tool() != "box" or self._start is None:
            return
        _box = np.array([np.minimum(self._start, point), np.maximum(self._start, point)], dtype=float)
        self.clear_transient()
        if np.all(_box[1] - _box[0] >= self._e.min_size):
            self._e.box.emit(_box, "box")

    def right(self, point) -> None:
        if self._e.tool() == "polygon" and self._points:
            self._points.pop()
            self._show_polygon(point)

    # ── 다각형 ────────────────────────────────────────────────────────────────
    def _show_polygon(self, cursor) -> None:
        """찍은 점 + 커서까지. 점이 셋 이상이면 닫은 꼴로."""
        self._preview.clear()
        if self._points:
            self._show(self._points + [cursor], closed=len(self._points) >= 3)

    def _close(self) -> None:
        if self._e.tool() != "polygon" or not self._e.isEnabled() or len(self._points) < 3:
            return
        _v = np.asarray(self._points, dtype=float)
        if np.any(_v.max(axis=0) - _v.min(axis=0) < self._e.min_size):
            return                                      # 역치보다 작음 - 점은 둠, 더 찍을 수 있게
        self.clear_transient()
        self._e.vertices.emit(_v, True, 0.0, "polygon")

    def clear_transient(self) -> None:
        self._start = None
        self._points = []
        self._preview.clear()

    def busy(self) -> bool:
        return self._start is not None or bool(self._points)
