"""겹침 층 - `Shape_Layer`(꺾은선, 다각형, 원), `Piece_Layer`(영상 조각). `Raster_editor.add_layer` 로 얹음.

- 좌표는 원본 픽셀 - `Raster_editor` 장면 좌표
- 펜 굵기는 화면 px - 확대해도 같은 굵기
- 층은 그리기만 - 무엇을 넣을지는 부르는 쪽
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsPathItem, QGraphicsPixmapItem

from ._view import to_qimage

__all__ = ["Piece_Layer", "Shape_Layer"]


def _pen(color: QColor, width: float) -> QPen:
    """화면 px 굵기 펜."""
    pen = QPen(color, width)
    pen.setCosmetic(True)
    return pen


class Shape_Layer(QGraphicsItemGroup):
    """부르는 쪽이 넘기는 모양 - 꺾은선 / 다각형 하나, 원 하나."""

    def __init__(self):
        super().__init__()
        self._line = QGraphicsPathItem()
        self._circle = QGraphicsPathItem()
        self.addToGroup(self._line)
        self.addToGroup(self._circle)

    def set_polyline(self, points, color: QColor, closed: bool = False) -> None:
        """꺾은선. `closed` 면 다각형 - 끝을 처음으로 잇고 옅게 채움. 꼭짓점 없으면 지움."""
        path = QPainterPath()
        pts = [QPointF(float(x), float(y)) for x, y in points]
        if pts:
            path.moveTo(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            if closed:
                path.closeSubpath()
        self._line.setPath(path)
        self._line.setPen(_pen(color, 1.5))
        fill = QColor(color)
        fill.setAlphaF(0.2)
        self._line.setBrush(QBrush(fill) if closed else QBrush(Qt.BrushStyle.NoBrush))

    def set_circle(self, center, radius: float, color: QColor) -> None:
        """원 하나. `center` 가 `None` 이면 지움."""
        path = QPainterPath()
        if center is not None:
            path.addEllipse(QPointF(float(center[0]), float(center[1])), radius, radius)
        self._circle.setPath(path)
        self._circle.setPen(_pen(color, 1.0))

    def clear(self) -> None:
        self._line.setPath(QPainterPath())
        self._circle.setPath(QPainterPath())


class Piece_Layer(QGraphicsItemGroup):
    """영상 조각 - 원본 px 자리 `(x, y, w, h)` 에 늘려 놓음. 뒤 조각이 앞을 덮음."""

    def __init__(self):
        super().__init__()
        self._items: list[QGraphicsPixmapItem] = []

    def set_pieces(self, pieces: list[tuple[tuple[int, int, int, int], np.ndarray]]) -> None:
        """`((x, y, w, h), 영상)` 목록으로 다시 놓음. 빈 목록이면 비움."""
        for item in self._items:
            self.removeFromGroup(item)
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._items = []
        for (x, y, w, h), image in pieces:
            item = QGraphicsPixmapItem(QPixmap.fromImage(to_qimage(image)))
            item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
            item.setTransform(QTransform.fromScale(w / image.shape[1], h / image.shape[0]))
            item.setPos(x, y)
            self.addToGroup(item)
            self._items.append(item)
