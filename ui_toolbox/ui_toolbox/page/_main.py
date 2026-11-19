"""main 골격 - root page. config 를 central widget 에 채움, 닫힐 때 멈출 것을 모아 둠.

- `QMainWindow` 는 제 layout 이 있음 - `Fill` 은 central widget 에
- root 묶음(`items`, `link`, `action`)을 그대로 올림. `find` 는 `items.find` - `QWidget.find`(정적, WId)를 여기서만 가림
- 공통 style(`Base`)이 root 의 `style` 아래에 깔림
- 상태, 입력의 뜻, 연결은 상속한 소비처 page
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMainWindow, QWidget
from python_toolbox.file import Make_dict_from

from ._style import Base, Tokens
from .builder import Fill

__all__ = ["Main"]


class Main(QMainWindow):
    """root page 하나.

    Attributes:
        items: root 의 배치에 드는 node
        link: root 의 popup
        action: root 의 `QAction`
    """

    def __init__(self, config: dict | str | Path, base: str | Path = ".", tokens: dict[str, Any] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        config: root node, 또는 그것을 담은 yaml 경로 - 경로면 `base` 는 그 폴더.
        base: `items` 파일 경로의 기준 폴더.
        tokens: 덮을 토큰 - `Tokens` 의 이름.
        parent: 부모 위젯.

        Raises:
            ValueError: config 파일을 맵으로 못 읽을 때. 나머지는 `Fill`, `Tokens` 와 같음.
        """
        super().__init__(parent)
        if not isinstance(config, dict):
            _path = Path(config)
            _ok, _data = Make_dict_from(_path)
            if not _ok or not isinstance(_data, dict):
                raise ValueError(f"cannot read a map from {_path}")
            config, base = _data, _path.parent
        self._stops: list[Callable[[], Any]] = []
        _body = QWidget()
        Fill(_body, config, base, Base(Tokens(**(tokens or {}))))
        self.setCentralWidget(_body)
        self.setWindowTitle(config.get("title", ""))
        self.items = _body.items
        self.link = _body.link
        self.action = _body.action

    def find(self, path: str) -> Any:
        """`items.find` - `.` 으로 이은 key 경로의 객체.

        Raises:
            KeyError: 없는 key 일 때, 중간 segment 가 container 가 아닐 때.
        """
        return self.items.find(path)

    def on_close(self, stop: Callable[[], Any]) -> None:
        """창이 닫힐 때 부를 것 - 감시, 타이머, 프로세스 멈춤. 넣은 차례로 부름."""
        self._stops.append(stop)

    def closeEvent(self, event) -> None:
        for _stop in self._stops:
            _stop()
        super().closeEvent(event)
