"""라스터 캔버스 - 2D 이미지. 캔버스 계약의 첫 구현.

포인터를 원본 픽셀 좌표로 낸다. 줌·스크롤과 무관하게 늘 원본 기준.
"""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ....style import SURFACE, Mark
from ..._canvas import Canvas
from ._convert import _bgr_to_pixmap, _gray_to_pixmap


class Raster_canvas(Canvas):
    """스크롤·줌을 지원하는 라스터 뷰.

    ``QScrollArea`` 안에 ``QLabel`` 을 두고 줌 상태에 따라 픽스맵을 다시 그린다.

    Note:
        ``zoom`` 이 None 이면 뷰포트에 맞춰 자동 리스케일(fit), float 이면 원본 픽셀 기준 절대
        배율로 고정. fit 모드에서는 창 리사이즈 시 다시 맞춘다.
    """

    _STEP = 1.15
    _ZOOM_MIN = 0.05
    _ZOOM_MAX = 8.0

    def __init__(self, placeholder: str = "이미지 없음",
                 parent: QWidget | None = None) -> None:
        """뷰를 구성한다.

        Args:
            placeholder: 이미지가 없을 때 표시할 안내 문구.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._src: QPixmap | None = None
        self._zoom: float | None = None  # None = fit-to-viewport
        self._interactive = False

        self._inner = QLabel(placeholder)
        self._inner.setAlignment(Qt.AlignCenter)
        self._inner.installEventFilter(self)   # 라벨 위 마우스 → 원본좌표 시그널

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._inner)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        Mark(self._scroll, SURFACE)
        self._scroll.viewport().installEventFilter(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._scroll)

        self.setMinimumSize(160, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)   # 클릭하면 키보드 포커스가 딸려온다 (바로 단축키 편집)

    def set_interactive(self, on: bool) -> None:
        """마우스 좌표 시그널(원본 픽셀) 방출을 켠다/끈다.

        Args:
            on: True면 라벨 위 press/move/release 를 원본 좌표로 emit (move 추적 포함).
        """
        self._interactive = on
        self._inner.setMouseTracking(on)   # 버튼 안 눌러도 move 추적 (미리보기용)

    def _to_orig(self, posf) -> tuple[int, int] | None:
        """라벨-로컬 좌표를 원본 이미지 픽셀 좌표로 환산한다 (범위로 클램프).

        Args:
            posf: 라벨 기준 마우스 위치 (``QPointF``).

        Returns:
            원본 픽셀 ``(x, y)``. 표시 중인 이미지가 없으면 None.
        """
        if self._src is None:
            return None
        _scale = self.effective_zoom() or 1.0
        _w, _h = self._src.width(), self._src.height()
        _x = max(0, min(_w - 1, int(posf.x() / _scale)))
        _y = max(0, min(_h - 1, int(posf.y() / _scale)))
        return _x, _y

    # ── public API ────────────────────────────────────────────────────────────

    def set_image(self, img_bgr: np.ndarray) -> None:
        """BGR 이미지를 표시한다.

        Args:
            img_bgr: BGR uint8 이미지 ``(H, W, 3)``.
        """
        self._src = _bgr_to_pixmap(img_bgr)
        self._render()

    def set_pixmap_source(self, pix: QPixmap) -> None:
        """픽스맵을 직접 표시한다.

        Args:
            pix: 표시할 ``QPixmap``.
        """
        self._src = pix
        self._render()

    def set_mask(self, mask: np.ndarray) -> None:
        """단일 채널 마스크를 표시한다.

        Args:
            mask: 단일 채널 uint8 이미지 ``(H, W)``.
        """
        self.set_pixmap_source(_gray_to_pixmap(mask))

    def clear_image(self, msg: str = "이미지 없음") -> None:
        """이미지를 지우고 안내 문구를 표시한다.

        Args:
            msg: 비운 뒤 보여줄 문구.
        """
        self._src = None
        self._inner.clear()
        self._inner.setText(msg)

    def source_size(self) -> tuple[int, int] | None:
        """지금 표시 중인 이미지 크기 ``(H, W)`` — 없으면 None (빈 라스터를 이 크기로 만든다)."""
        if self._src is None:
            return None
        return self._src.height(), self._src.width()

    def set_zoom(self, zoom: float) -> None:
        """절대 배율로 줌한다 (허용 범위로 클램프).

        Args:
            zoom: 원본 픽셀 기준 배율.
        """
        self._zoom = max(self._ZOOM_MIN, min(self._ZOOM_MAX, zoom))
        self._render()
        self.zoom_changed.emit(self._zoom)

    def reset_zoom(self) -> None:
        """fit-to-viewport 모드로 되돌린다."""
        self._zoom = None
        self._render()
        self.zoom_changed.emit(0.0)

    def effective_zoom(self) -> float:
        """현재 유효 배율을 반환한다.

        Returns:
            fit 모드면 계산된 맞춤 배율, 아니면 설정된 절대 배율.
        """
        return self._fit_scale() if self._zoom is None else self._zoom

    def center_on(self, x: float, y: float) -> None:
        """원본 픽셀 좌표 ``(x, y)`` 가 뷰포트 중앙에 오도록 스크롤한다.

        스크롤바 범위로 자동 클램프된다 (fit 모드라 이미지가 다 보이면 사실상 no-op).

        Args:
            x: 중앙에 둘 원본 픽셀 x.
            y: 중앙에 둘 원본 픽셀 y.
        """
        if self._src is None:
            return
        _scale = self.effective_zoom()
        _hbar = self._scroll.horizontalScrollBar()
        _vbar = self._scroll.verticalScrollBar()
        _hbar.setValue(int(x * _scale - self._scroll.viewport().width() / 2))
        _vbar.setValue(int(y * _scale - self._scroll.viewport().height() / 2))

    # ── internals ─────────────────────────────────────────────────────────────

    def _fit_scale(self) -> float:
        """원본을 뷰포트에 맞추는 배율을 계산한다."""
        if self._src is None:
            return 1.0
        vw = max(1, self._scroll.viewport().width())
        vh = max(1, self._scroll.viewport().height())
        return min(vw / self._src.width(), vh / self._src.height())

    def _render(self) -> None:
        """현재 배율로 픽스맵을 다시 그린다."""
        if self._src is None:
            return
        scale = self.effective_zoom()
        w = max(1, int(self._src.width() * scale))
        h = max(1, int(self._src.height() * scale))
        self._inner.setPixmap(
            self._src.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self._inner.resize(w, h)

    def resizeEvent(self, event) -> None:
        """fit 모드일 때 리사이즈에 맞춰 다시 그린다."""
        super().resizeEvent(event)
        if self._zoom is None:
            self._render()

    def eventFilter(self, obj, event) -> bool:
        """뷰포트 휠(줌)·라벨 마우스(원본좌표 시그널) 이벤트를 가로챈다.

        Returns:
            휠 이벤트를 처리했으면 True, 그 외(마우스 포함)는 기본 처리로 위임.
        """
        if obj is self._inner and self._interactive and self._src is not None:
            _et = event.type()
            if _et == QEvent.Type.MouseButtonPress:
                self.setFocus(Qt.FocusReason.MouseFocusReason)   # 클릭 = 선택하고 바로 단축키로 편집
            if _et == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                _p = self._to_orig(event.position())
                if _p is not None:
                    self.mouse_pressed.emit(*_p)
            elif _et == QEvent.Type.MouseButtonPress and event.button() == Qt.RightButton:
                _p = self._to_orig(event.position())
                if _p is not None:
                    self.mouse_right_pressed.emit(*_p)
            elif _et == QEvent.Type.MouseMove:
                _p = self._to_orig(event.position())
                if _p is not None:
                    self.mouse_moved.emit(*_p)
            elif _et == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
                _p = self._to_orig(event.position())
                if _p is not None:
                    self.mouse_released.emit(*_p)
            # 관찰만 — 라벨 기본 처리는 막지 않는다

        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            factor = self._STEP if delta > 0 else 1.0 / self._STEP
            old = self.effective_zoom()
            new = max(self._ZOOM_MIN, min(self._ZOOM_MAX, old * factor))

            mouse = event.position().toPoint()
            hbar = self._scroll.horizontalScrollBar()
            vbar = self._scroll.verticalScrollBar()

            self._zoom = new
            self._render()
            self.zoom_changed.emit(new)

            # 줌 중에도 커서 아래 픽셀이 제자리에 머물도록 스크롤 보정
            ratio = new / old
            hbar.setValue(int((hbar.value() + mouse.x()) * ratio - mouse.x()))
            vbar.setValue(int((vbar.value() + mouse.y()) * ratio - mouse.y()))
            return True
        return super().eventFilter(obj, event)
