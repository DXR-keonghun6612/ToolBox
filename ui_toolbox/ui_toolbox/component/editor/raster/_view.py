"""raster 보기 - 영상 한 장과 겹침 층, 확대 / 이동, 포인터를 원본 픽셀 좌표로. `Raster_editor` 의 캔버스.

- 장면 좌표 = 원본 픽셀. 픽셀 `(x, y)` 는 `[x, x + 1) x [y, y + 1)`. 좌표는 실수로 냄 - 정수 격자는 쓰는 쪽이 자름
- 확대 / 이동은 보기 변환만 - 영상, 층을 다시 그리지 않음. 휠 = 커서 자리 고정 확대, 가운데 버튼 / Ctrl + 왼쪽 드래그 = 이동
- 포인터 신호는 늘 냄 - 막는 것은 편집기
- 층은 `QGraphicsItem` - `add_layer` 의 z 차례로 겹침
- 영상을 바꾸면 맞춤(fit)으로 돌아감 - `keep_view` 면 크기가 같을 때 위치, 배율 유지. 창 크기가 바뀌면 맞춤일 때만 다시 맞춤
- `set_crop` : 보이는 범위만 제한 - 영상, 좌표는 그대로 원본 픽셀. 범위 밖은 바탕색으로 덮고 포인터는 범위 안으로 자름
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

__all__ = ["STEP", "ZOOM_MAX", "ZOOM_MIN", "to_qimage"]

#: 휠 한 칸 배율, 배율 범위
STEP, ZOOM_MIN, ZOOM_MAX = 1.15, 0.02, 64.0


def to_qimage(image: np.ndarray) -> QImage:
    """gray `(H, W)` uint8 / uint16, BGR `(H, W, 3)` / BGRA `(H, W, 4)` uint8 -> `QImage`. 픽셀을 복사함 - 원본 배열과 안 묶임.

    Raises:
        ValueError: 모양 / 타입 밖.
    """
    a = np.ascontiguousarray(image)
    h, w = a.shape[:2]
    if a.ndim == 2 and a.dtype == np.uint16:
        return QImage(a.data, w, h, 2 * w, QImage.Format.Format_Grayscale16).copy()
    if a.dtype != np.uint8:
        raise ValueError(f"image {a.dtype} {a.shape} - expected uint8, or uint16 for gray")
    if a.ndim == 2:
        return QImage(a.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    if a.ndim == 3 and a.shape[2] == 3:
        return QImage(a.data, w, h, 3 * w, QImage.Format.Format_BGR888).copy()
    if a.ndim == 3 and a.shape[2] == 4:
        return QImage(a.data, w, h, 4 * w, QImage.Format.Format_ARGB32).copy()   # 작은 끝 기계에서 BGRA 차례
    raise ValueError(f"image shape {a.shape} - expected (H, W) / (H, W, 3) / (H, W, 4)")


class _View(QGraphicsView):
    """영상 장면과 그 보기. 포인터를 원본 픽셀 좌표로 냄.

    Attributes:
        pressed: 좌클릭 `(x, y)`.
        moved: 포인터 이동 `(x, y)`. 누르지 않아도 남.
        released: 좌클릭 해제 `(x, y)`, 끌었나 - 누른 자리에서 `startDragDistance`(화면 px) 이상 움직임.
        right_pressed: 우클릭 `(x, y)`.
        zoom_changed: 유효 배율. `0.0` 은 맞춤.
    """

    pressed       = Signal(object)
    moved         = Signal(object)
    released      = Signal(object, bool)
    right_pressed = Signal(object)
    zoom_changed  = Signal(float)

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        super().__init__(self._scene)
        self._scene.setParent(self)
        self._image = QGraphicsPixmapItem()
        self._image.setZValue(0)
        self._image.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self._scene.addItem(self._image)
        self._size: tuple[int, int] | None = None
        self._array: np.ndarray | None = None           # 받은 영상 그대로 - 미리보기가 아래 픽셀을 읽음
        self._crop: QRectF | None = None
        self._fit = True
        self._pan: QPointF | None = None
        self._down: QPointF | None = None               # 좌클릭을 누른 화면 자리 - 끌기 판정
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)   # 확대하면 픽셀이 칸으로 보이게
        self.setMouseTracking(True)
        self.setMinimumSize(160, 120)

    # ── 영상, 층 ──────────────────────────────────────────────────────────────
    def set_image(self, image: np.ndarray, keep_view: bool) -> None:
        q = to_qimage(image)
        self._image.setPixmap(QPixmap.fromImage(q))
        self._array = image
        same = self._size == (q.height(), q.width())
        self._size = (q.height(), q.width())
        if keep_view and same:
            return
        self._apply_range()
        self.reset_zoom()

    def clear_image(self) -> None:
        self._image.setPixmap(QPixmap())
        self._size = None
        self._array = None

    def image(self) -> np.ndarray | None:
        return self._array

    def crop(self) -> QRectF | None:
        return self._crop

    def set_crop(self, rect: tuple[int, int, int, int] | None) -> None:
        crop = None if rect is None else QRectF(*rect)
        if crop == self._crop:
            return
        self._crop = crop
        if self._size is not None:
            self._apply_range()
            self.reset_zoom()
        self.viewport().update()

    def _apply_range(self) -> None:
        h, w = self._size
        self._scene.setSceneRect(self._crop if self._crop is not None else QRectF(0, 0, w, h))

    def source_size(self) -> tuple[int, int] | None:
        return self._size

    def add_layer(self, item: QGraphicsItem, z: float) -> None:
        if z <= 0:
            raise ValueError(f"z {z} - must be above the image (0)")
        item.setZValue(z)
        self._scene.addItem(item)

    # ── 확대 ──────────────────────────────────────────────────────────────────
    def is_fit(self) -> bool:
        return self._fit

    def effective_zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, zoom: float) -> None:
        z = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        t = self.transform()
        self.setTransform(t.scale(z / t.m11(), z / t.m11()))
        self._fit = False
        self.zoom_changed.emit(z)

    def reset_zoom(self) -> None:
        if self._size is None:
            return
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._fit = True
        self.zoom_changed.emit(0.0)

    def focus(self, x: int, y: int, w: int, h: int, pad: float) -> None:
        seen = self.mapToScene(self.viewport().rect()).boundingRect()
        if self._fit or w > seen.width() or h > seen.height():
            m = max(w, h) * pad
            self.fitInView(QRectF(x - m, y - m, w + 2 * m, h + 2 * m), Qt.AspectRatioMode.KeepAspectRatio)
            self.set_zoom(max(ZOOM_MIN, min(ZOOM_MAX, self.effective_zoom())))
        self.centerOn(x + w / 2, y + h / 2)

    # ── Qt 이벤트 ─────────────────────────────────────────────────────────────
    def drawForeground(self, painter, rect):
        if self._crop is None:
            return
        outside = QPainterPath()
        outside.addRect(rect)
        inner = QPainterPath()
        inner.addRect(self._crop)
        painter.fillPath(outside.subtracted(inner), self.palette().window())

    def wheelEvent(self, event):
        before = self.mapToScene(event.position().toPoint())
        self.set_zoom(self.effective_zoom() * (STEP if event.angleDelta().y() > 0 else 1.0 / STEP))
        d = self.mapToScene(event.position().toPoint()) - before
        self.translate(d.x(), d.y())

    def mousePressEvent(self, event):
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and ctrl):
            self._pan = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        p = self._point(event)
        if p is not None and event.button() == Qt.MouseButton.LeftButton:
            self._down = event.position()
            self.pressed.emit(p)
        elif p is not None and event.button() == Qt.MouseButton.RightButton:
            self.right_pressed.emit(p)

    def mouseMoveEvent(self, event):
        if self._pan is not None:
            d = event.position() - self._pan
            self._pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        p = self._point(event)
        if p is not None:
            self.moved.emit(p)

    def mouseReleaseEvent(self, event):
        if self._pan is not None:
            self._pan = None
            self.unsetCursor()
            return
        p = self._point(event)
        if p is not None and event.button() == Qt.MouseButton.LeftButton and self._down is not None:
            _dragged = (event.position() - self._down).manhattanLength() >= QApplication.startDragDistance()
            self._down = None
            self.released.emit(p, _dragged)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.reset_zoom()

    def _point(self, event) -> tuple[float, float] | None:
        """이벤트 자리 -> 원본 픽셀 좌표. 영상 밖은 영상 안으로 자름. 영상 없으면 None."""
        if self._size is None:
            return None
        p = self.mapToScene(event.position().toPoint())
        h, w = self._size
        r = self._crop if self._crop is not None else QRectF(0, 0, w, h)
        return (min(max(p.x(), max(r.left(), 0.0)), min(r.right(), w) - 1e-6),
                min(max(p.y(), max(r.top(), 0.0)), min(r.bottom(), h) - 1e-6))
