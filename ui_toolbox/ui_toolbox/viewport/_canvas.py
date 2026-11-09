"""캔버스 계약 - 포인터를 2D 도메인 좌표로 내는 화면.

무슨 좌표인지는 구현이 안다 - 라스터면 원본 픽셀. 계약은 좌표의 뜻을 묻지 않는다.

포인터가 늘 어딘가에 맞으므로 신호가 좌표만 싣는다. 빗나감이 있는 화면(3D 장면)은 이 계약이
아니라 자기 계약을 쓴다 - `맞았나` 를 실어야 한다.

좌표를 실수로 내는 이유 - 픽셀 격자는 정수지만 구현이 늘 격자일 필요는 없다. 정수 격자를 쓰는
쪽이 자기 자리에서 자른다.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class Canvas(QWidget):
    """포인터 · 보기 계약. 구현이 좌표계와 그리기를 든다.

    Attributes:
        mouse_pressed: 좌클릭 ``(x, y)``.
        mouse_moved: 포인터 이동 ``(x, y)``.
        mouse_released: 좌클릭 해제 ``(x, y)``.
        mouse_right_pressed: 우클릭 ``(x, y)``. 그리던 것 취소용.
        zoom_changed: 유효 배율. ``0.0`` 은 fit.
    """

    mouse_pressed       = Signal(float, float)
    mouse_moved         = Signal(float, float)
    mouse_released      = Signal(float, float)
    mouse_right_pressed = Signal(float, float)
    zoom_changed        = Signal(float)

    def set_interactive(self, on: bool) -> None:
        """포인터 신호 방출을 켜고 끈다.

        Args:
            on: True 면 포인터를 도메인 좌표로 환산해 신호로 낸다.
        """
        raise NotImplementedError
