"""테스트 전역 - 화면 없이 도는 Qt 앱 하나.

`QT_QPA_PLATFORM` 을 여기서 세움 - 부르는 쪽이 환경변수를 안 걸어도 되게.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # QApplication 보다 먼저

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def _qt_app() -> QApplication:
    """프로세스에 하나. 위젯을 짓기 전에 서 있어야 함."""
    return QApplication.instance() or QApplication([])
