"""획 도구 - 브러시, 지우개. 궤적과 반경으로 칠하는 일을 함께 씀.

- 끌기. 뗄 때 `vertices(궤적, 닫힘 거짓, 반경, 표시)` - 표시가 칠하기 / 지우기를 가름
- 미리보기는 받는 쪽과 같은 래스터화(`_ops.Rasterize`) - 브러시는 강조색 옅게, 지우개는 원본 영상을 덮어 지워진 것처럼.
  외곽선 없음 - 끄는 동안 연산을 아낌
- 옵션 - 반경(원본 1 px 단위 정수). 처음 값은 편집기의 `brush_radius`. `[` `]` 는 `brush_step / 확대 비율` 을 반올림한 만큼,
  최소 1 px - 확대하면 잘게, 축소하면 크게. 획 도구를 고른 동안만
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox

from .._base import Draw_tool
from .._tool import Tool
from ._ops import Rasterize
from ._preview import Preview

__all__ = ["Stroke_tool"]

#: 미리보기 층의 z.
_Z = 900.0


class Stroke_tool(Draw_tool):
    """브러시, 지우개."""

    TOOLS = (Tool("brush", "edit", "🖌", "브러시", "B", "끌어서 칠함"),
             Tool("eraser", "edit", "⌫", "지우개", "E", "끌어서 지움"))

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self._preview = Preview(editor, _Z)
        self._path: list[tuple[float, float]] | None = None
        self._radius = QSpinBox()
        self._radius.setRange(1, 500)
        self._radius.setValue(editor.brush_radius)
        for _seq, _sign in (("[", -1.0), ("]", 1.0)):
            _sc = QShortcut(QKeySequence(_seq), editor)
            _sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            _sc.activated.connect(lambda s=_sign: self._step(s))

    def _step(self, sign: float) -> None:
        """반경을 `brush_step / 확대 비율` 을 반올림한 만큼, 최소 1 px 바꿈. 범위는 숫자 칸이 자름. 획 도구를 고른 동안만."""
        if self._e.tool() not in ("brush", "eraser"):
            return
        _amount = max(1, round(self._e.brush_step / self._e.effective_zoom()))
        self._radius.setValue(self._radius.value() + int(sign) * _amount)
        if self._path is not None:
            self._show()

    def build_options(self, row: QHBoxLayout) -> None:
        row.addWidget(QLabel("반경"))
        row.addWidget(self._radius)

    def press(self, point) -> None:
        self._path = [point]
        self._show()

    def move(self, point) -> None:
        if self._path is not None:
            self._path.append(point)
            self._show()

    def release(self, point) -> None:
        if self._path is None:
            return
        _v = np.asarray(self._path + [point], dtype=float)
        _key = self._e.tool()
        self.clear_transient()
        self._e.vertices.emit(_v, False, float(self._radius.value()), _key)

    def _show(self) -> None:
        """궤적을 받는 쪽과 같은 래스터화로 - 브러시는 강조색 옅게, 지우개는 원본."""
        _size = self._e.source_size()
        if _size is None or not self._path:
            return
        _mask = Rasterize(np.asarray(self._path, dtype=float), False, float(self._radius.value()), _size)
        self._preview.fill(_mask, original=self._e.tool() == "eraser")

    def clear_transient(self) -> None:
        self._path = None
        self._preview.clear()

    def busy(self) -> bool:
        return self._path is not None
