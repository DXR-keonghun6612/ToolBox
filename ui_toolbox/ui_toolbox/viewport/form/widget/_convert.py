"""numpy(BGR · gray) -> `QPixmap` 변환. `_raster` 만 씀."""

from __future__ import annotations

import cv2
import numpy as np

from PySide6.QtGui import QImage, QPixmap


def _bgr_to_pixmap(img_bgr: np.ndarray) -> QPixmap:
    """BGR ndarray를 ``QPixmap`` 으로 변환한다.

    Args:
        img_bgr: OpenCV 관례의 BGR uint8 이미지 ``(H, W, 3)``.

    Returns:
        RGB로 변환한 ``QPixmap``.
    """
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = img_rgb.shape
    q_img = QImage(img_rgb.data.tobytes(), w, h, w * ch, QImage.Format_RGB888)
    return QPixmap.fromImage(q_img)


def _gray_to_pixmap(mask: np.ndarray) -> QPixmap:
    """그레이스케일/마스크 ndarray를 ``QPixmap`` 으로 변환한다.

    Args:
        mask: 단일 채널 uint8 이미지 ``(H, W)``.

    Returns:
        그레이를 BGR로 펼쳐 변환한 ``QPixmap``.
    """
    return _bgr_to_pixmap(cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR))
