"""raster 편집기 - 영상 보기와 편집을 하나로. 도구가 없으면 보기.

보기(확대, 이동, 자르기, 층)는 [`_view`](_view.py), 도구 연결은 [`Editor_base`](../_base.py).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Signal
from PySide6.QtWidgets import QGraphicsItem, QWidget

from .._base import Draw_tool, Editor_base
from ._preview import Preview
from ._shape import Shape_tool
from ._stroke import Stroke_tool
from ._view import _View

#: 올가미 미리보기 층의 z - 다른 층보다 위.
_LASSO_Z = 1_000.0

__all__ = ["Raster_editor"]


class Raster_editor(Editor_base):
    """영상 한 장 + 겹침 층 + 도구. 좌표는 원본 픽셀 `(x, y)`, `D = 2`.

    Attributes:
        hovered: 커서 자리 `(x, y)`. 도구, 잠금과 상관없이 늘.
        zoom_changed: 유효 배율. `0.0` 은 맞춤.
    """

    TOOL_TYPES: tuple[type[Draw_tool], ...] = (Shape_tool, Stroke_tool)

    hovered      = Signal(object)
    zoom_changed = Signal(float)

    def __init__(self, tools: list[str] | None = None, toolbar: str | None = "top", options: str | None = "top",
                 brush_radius: int = 5, brush_step: float = 1.0, min_size: int = 3,
                 parent: QWidget | None = None) -> None:
        """Args:
        tools: 쓸 도구 `key` 목록. 비면 보기.
        toolbar: 툴바 자리 - `top`, `bottom`, `left`, `right`, `None`(안 놓음, 멤버로). 왼쪽 · 오른쪽이면 버튼이 세로.
        options: 옵션 자리 - `top`, `bottom`, `None`(안 놓음, 멤버로).
        brush_radius: 획 도구의 처음 반경(원본 px, 정수).
        brush_step: 반경 단축키 한 번의 고정 값 - 실제 바뀌는 양은 이 값 / 확대 비율을 반올림, 최소 1 px.
        min_size: 상자, 다각형을 내는 역치(원본 px) - 가로, 세로가 이 값보다 작으면 안 냄.
        parent: 부모 위젯.
        """
        self.brush_radius = int(brush_radius)
        self.brush_step = float(brush_step)
        self.min_size = int(min_size)
        self._view = _View()
        super().__init__(self._view, list(tools or []), toolbar, options, parent)
        self._lasso_preview = Preview(self, _LASSO_Z)
        self._view.pressed.connect(self._press)
        self._view.moved.connect(self._move)
        self._view.moved.connect(self.hovered)
        self._view.released.connect(self._release)
        self._view.right_pressed.connect(self._right)
        self._view.zoom_changed.connect(self.zoom_changed)

    def _show_lasso(self, points: list[tuple[float, ...]] | None) -> None:
        """올가미 - 경로 이중 외곽선. 안쪽은 그대로."""
        if points is None:
            self._lasso_preview.clear()
            return
        self._lasso_preview.outline(points, closed=False)

    def image(self) -> np.ndarray | None:
        """지금 영상 배열 - `set_image` 가 받은 그대로. 없으면 None."""
        return self._view.image()

    # ── 영상, 층 ──────────────────────────────────────────────────────────────
    def set_image(self, image: np.ndarray, keep_view: bool = False) -> None:
        """영상을 바꿈. gray uint8 / uint16, BGR / BGRA uint8. `keep_view` 이고 크기가 같으면 위치, 배율 유지, 아니면 맞춤으로."""
        self._view.set_image(image, keep_view)

    def clear_image(self) -> None:
        self._view.clear_image()

    def crop(self) -> QRectF | None:
        """보이는 범위. 없으면 None."""
        return self._view.crop()

    def set_crop(self, rect: tuple[int, int, int, int] | None) -> None:
        """보이는 범위 `(x, y, w, h)` - 원본 픽셀. None 이면 영상 전체. 맞춤으로 돌아감."""
        self._view.set_crop(rect)

    def source_size(self) -> tuple[int, int] | None:
        """지금 영상 `(H, W)`. 없으면 None."""
        return self._view.source_size()

    def add_layer(self, item: QGraphicsItem, z: float) -> None:
        """층 하나를 얹음. `z` 가 클수록 위. 영상은 0.

        Raises:
            ValueError: `z` 가 0 이하일 때 - 영상 아래로 감.
        """
        self._view.add_layer(item, z)

    # ── 확대 ──────────────────────────────────────────────────────────────────
    def is_fit(self) -> bool:
        return self._view.is_fit()

    def effective_zoom(self) -> float:
        """지금 배율 - 화면 px / 원본 px."""
        return self._view.effective_zoom()

    def set_zoom(self, zoom: float) -> None:
        """절대 배율. 범위로 자름."""
        self._view.set_zoom(zoom)

    def reset_zoom(self) -> None:
        """영상 전체가 보이게 맞춤."""
        self._view.reset_zoom()

    def center_on(self, x: float, y: float) -> None:
        """원본 픽셀 `(x, y)` 를 가운데로."""
        self._view.centerOn(x, y)

    def focus(self, x: int, y: int, w: int, h: int, pad: float) -> None:
        """원본 영역 `(x, y, w, h)` 를 가운데로. 맞춤이거나 영역이 화면에 안 들어가면 영역 +- 크기 x `pad` 에 맞춰 확대."""
        self._view.focus(x, y, w, h, pad)
