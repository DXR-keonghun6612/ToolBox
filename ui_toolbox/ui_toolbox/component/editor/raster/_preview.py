"""raster 미리보기 - 아직 데이터가 아닌 것(그리는 중인 도형, 획)을 영상 위에 보임. 아래 영상의 정보는 지킴.

- 채움 두 갈래 - 옅은 덮기(팔레트 강조색 반투명, 밝기 · 결이 남음), 원본(아래 영상을 그대로 덮어 위 층이 지워진 것처럼 보임)
- 외곽선 - 이중선(검정 실선 위 흰 점선). 밝은 바탕에서는 검정, 어두운 바탕에서는 흰색이 보임. 두 색은 style 이 아니라 어떤
  바탕에서도 보이게 하는 기능이라 고정
- 채움은 영역의 둘레 상자만큼만 잘라 칠함 - 큰 영상에서도 가벼움
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem

from ._layers import Piece_Layer

__all__ = ["Preview"]

#: 옅은 덮기 불투명도 0 .. 255.
_TINT = 64


def _bgr8(image: np.ndarray) -> np.ndarray:
    """영상 -> BGR uint8. gray uint8 / uint16, BGR, BGRA."""
    if image.ndim == 2:
        _g = (image >> 8).astype(np.uint8) if image.dtype == np.uint16 else image
        return np.repeat(_g[..., None], 3, axis=2)
    return image[..., :3]


def _line(color, dash: bool) -> QGraphicsPathItem:
    """화면 1 px 선 하나."""
    _pen = QPen(QColor(color), 1.0)
    _pen.setCosmetic(True)
    if dash:
        _pen.setStyle(Qt.PenStyle.DashLine)
    _item = QGraphicsPathItem()
    _item.setPen(_pen)
    return _item


class Preview:
    """채움 한 장 + 이중 외곽선. 편집기 장면에 얹음."""

    def __init__(self, editor, z: float) -> None:
        """Args:
        editor: 얹을 `Raster_editor` - `add_layer`, `image`, `palette` 를 씀.
        z: 층 z. 외곽선은 그 바로 위.
        """
        self._e = editor
        self._fill = Piece_Layer()
        self._dark = _line(Qt.GlobalColor.black, dash=False)
        self._light = _line(Qt.GlobalColor.white, dash=True)
        editor.add_layer(self._fill, z)
        editor.add_layer(self._dark, z + 0.5)
        editor.add_layer(self._light, z + 0.6)

    def fill(self, mask: np.ndarray, original: bool) -> None:
        """`mask` 자리를 칠함. 거짓이면 강조색 옅게, 참이면 원본 그대로. 영상이 없거나 칸이 없으면 지움."""
        _image = self._e.image()
        _ys, _xs = np.nonzero(mask) if _image is not None else ((), ())
        if len(_ys) == 0:
            self._fill.set_pieces([])
            return
        _y0, _y1, _x0, _x1 = _ys.min(), _ys.max() + 1, _xs.min(), _xs.max() + 1
        _sel = mask[_y0:_y1, _x0:_x1]
        _bgra = np.zeros((_y1 - _y0, _x1 - _x0, 4), np.uint8)
        if original:
            _bgra[..., :3] = _bgr8(_image[_y0:_y1, _x0:_x1])
            _bgra[..., 3] = np.where(_sel, 255, 0)
        else:
            _c = self._e.palette().highlight().color()
            _bgra[..., :3] = (_c.blue(), _c.green(), _c.red())
            _bgra[..., 3] = np.where(_sel, _TINT, 0)
        self._fill.set_pieces([((int(_x0), int(_y0), int(_x1 - _x0), int(_y1 - _y0)), _bgra)])

    def outline(self, points, closed: bool) -> None:
        """이중 외곽선."""
        _path = QPainterPath()
        _pts = [QPointF(float(_x), float(_y)) for _x, _y in points]
        if _pts:
            _path.moveTo(_pts[0])
            for _p in _pts[1:]:
                _path.lineTo(_p)
            if closed:
                _path.closeSubpath()
        self._dark.setPath(_path)
        self._light.setPath(_path)

    def clear(self) -> None:
        self._fill.set_pieces([])
        self._dark.setPath(QPainterPath())
        self._light.setPath(QPainterPath())
