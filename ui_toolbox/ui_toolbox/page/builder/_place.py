"""배치 - 위젯에 배치를 걸고 자식을 놓는 자리.

- `QLayout` 은 위젯에 `setLayout`. 제 자체가 배치인 위젯은 위젯 안에 하나 두고 자식을 거기에 - config, 경로에 안 보임
- 자식의 `title` 은 탭 글자, `add(child, title)` 계약의 위젯이 읽음. 나머지 배치는 안 읽음
- 메뉴 막대는 `QLayout` 이 있는 자리만
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLayout, QMenuBar, QTabWidget, QVBoxLayout, QWidget

__all__ = ["Arrange", "Make", "Place"]


def Make(cls: type, args: dict, where: str) -> Any:
    """`cls(**args)`.

    Raises:
        TypeError: 생성자가 인자를 안 받을 때 - 어느 node 인지 붙여서. PySide6 는 모르는 키워드를 `AttributeError` 로 냄
    """
    try:
        return cls(**args)
    except (TypeError, AttributeError) as _e:
        raise TypeError(f"{where}: cannot build {cls.__name__}({args}) - {_e}") from _e


class Place:
    """자식을 놓는 자리 - `QLayout` 또는 제 자체가 배치인 위젯."""

    def __init__(self, lay: QLayout | None, host: QWidget | None) -> None:
        self._lay = lay
        self._host = host
        self._bar: QMenuBar | None = None

    def add(self, child: QWidget, title: str) -> None:
        """자식 하나를 끝에."""
        if self._host is None:
            self._lay.addWidget(child)
        elif callable(getattr(self._host, "add", None)):
            self._host.add(child, title)
        elif isinstance(self._host, QTabWidget):
            self._host.addTab(child, title)
        else:
            self._host.addWidget(child)

    def menu_bar(self, where: str) -> QMenuBar:
        """메뉴 막대. 처음 부를 때 지어 layout 에 걺.

        Raises:
            TypeError: `QLayout` 이 없는 자리일 때 - 제 자체가 배치인 위젯.
        """
        if self._lay is None:
            raise TypeError(f"{where}.action.menu: a menu bar needs a QLayout node")
        if self._bar is None:
            self._bar = QMenuBar()
            self._lay.setMenuBar(self._bar)
        return self._bar


def Arrange(target: QWidget, cls: type, args: dict, where: str) -> Place:
    """`target` 에 배치를 걺. 제 자체가 배치인 위젯은 `target` 안에 하나 두고 자식을 거기에."""
    if issubclass(cls, QLayout):
        _lay = Make(cls, args, where)
        target.setLayout(_lay)
        return Place(_lay, None)
    _lay = QVBoxLayout(target)
    _lay.setContentsMargins(0, 0, 0, 0)
    _host = Make(cls, args, where)
    _lay.addWidget(_host)
    return Place(_lay, _host)
