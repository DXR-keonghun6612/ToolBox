"""앱 수명 - `QApplication` 을 세우고 page 를 띄우고 루프를 돎.

- 무엇을 띄우는지 모름 - page 를 짓는 콜러블을 받음
- palette 는 앱에 한 번, 같은 토큰을 콜러블에 넘김 - page(`Main`)의 공통 style 이 같은 토큰에서 나옴
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QApplication, QWidget

from .page import Palette, Tokens

__all__ = ["Run"]


def Run(build: Callable[[dict[str, Any]], QWidget], tokens: dict[str, Any] | None = None,
        size: tuple[int, int] = (1280, 860)) -> int:
    """앱을 세우고 page 를 띄운 뒤 루프를 돎.

    Args:
        build: 토큰 맵을 받아 page 를 짓는 콜러블 - `lambda t: My_page("page.yaml", tokens=t)`. palette 가 선 뒤에 불림.
        tokens: 덮을 토큰 - `Tokens` 의 이름.
        size: 창 크기 `(폭, 높이)`.

    Returns:
        프로세스 종료 코드.

    Raises:
        KeyError: 모르는 토큰 이름일 때.
    """
    _tokens = Tokens(**(tokens or {}))
    _app = QApplication.instance() or QApplication(sys.argv)
    _app.setStyle("Fusion")              # 플랫폼 테마가 palette 를 덮지 않게
    _app.setPalette(Palette(_tokens))
    _page = build(_tokens)
    _page.resize(*size)
    _page.show()
    return _app.exec()
