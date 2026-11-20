"""이름 -> 클래스, 클래스가 배치인가.

- `qt_` 로 시작하면 PySide6 `QtWidgets`, page 의 것(`Popup`, `Job_popup`)은 여기서, 나머지는 `component` 등록표
- 배치 - `QLayout`, 제 자체가 배치인 위젯(`QSplitter`, `QTabWidget`, `add(child, title)` 이 있는 위젯)
- 없는 이름은 실패, 기본으로 안 물러남
"""

from __future__ import annotations

from PySide6 import QtWidgets
from PySide6.QtWidgets import QLayout, QSplitter, QTabWidget, QWidget

from ... import component
from .._progress import Job_popup
from .._popup import Popup

__all__ = ["Find", "Find_at", "Is_class", "Is_host", "Is_layout", "PAGE", "QT"]

#: 이 접두가 붙으면 PySide6 에서 찾음.
QT = "qt_"

#: page 의 것 - 등록표 없이 여기서 앎.
PAGE: dict[str, type] = {"Popup": Popup, "Job_popup": Job_popup}

#: 제 자체가 배치인 Qt 위젯 - 자식을 바로 받음. 그 밖은 `add(child, title)` 계약.
_HOSTS = (QSplitter, QTabWidget)


def Find(name: str) -> type:
    """이름의 클래스.

    Raises:
        TypeError: 이름이 글자가 아닐 때.
        KeyError: 없는 이름일 때, page 의 것과 component 이름이 겹칠 때.
    """
    if not isinstance(name, str):
        raise TypeError(f"class must be str - got {name!r}")
    if name.startswith(QT):
        _cls = getattr(QtWidgets, name[len(QT):], None)
        if not isinstance(_cls, type):
            raise KeyError(f"not in PySide6 QtWidgets: {name!r}")
        return _cls
    if name in PAGE:
        if _registered(name):
            raise KeyError(f"name used by both page and component: {name!r}")
        return PAGE[name]
    return component.REGISTRY.Get(name)


def Find_at(name: str, where: str) -> type:
    """`Find` - 실패 글자에 node 자리를 붙임.

    Raises:
        TypeError, KeyError: `Find` 와 같음.
    """
    try:
        return Find(name)
    except KeyError as _e:
        raise KeyError(f"{where}: {_e.args[0]}") from _e


def _registered(name: str) -> bool:
    """component 등록표에 있나 - `Registry` 는 `Get` 만 있어 실패로 판정."""
    try:
        component.REGISTRY.Get(name)
    except KeyError:
        return False
    return True


def Is_class(name: str) -> bool:
    """클래스 이름인가 - Qt 위젯, page 의 것, component."""
    return isinstance(getattr(QtWidgets, name, None), type) or name in PAGE or _registered(name)


def Is_host(cls: type) -> bool:
    """제 자체가 배치인 위젯인가 - `QSplitter`, `QTabWidget`, 또는 `add(child, title)` 이 있는 위젯."""
    return issubclass(cls, QWidget) and (issubclass(cls, _HOSTS) or callable(getattr(cls, "add", None)))


def Is_layout(cls: type) -> bool:
    """배치 클래스인가 - `QLayout` 또는 제 자체가 배치인 위젯."""
    return issubclass(cls, QLayout) or Is_host(cls)
