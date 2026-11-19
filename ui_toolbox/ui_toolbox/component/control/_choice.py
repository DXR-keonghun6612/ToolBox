"""고르기 control - 후보 중 하나의 radio, combo. 후보 중 여럿의 check.

후보는 아무 값. 보이는 글자는 `str(후보)`, 값은 후보 그대로.
None 이 오면 기본으로 돌아감 - 기본은 값(`default`) 또는 번호(`default_at`) 하나로 줌.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QRadioButton,
    QWidget,
)

__all__ = ["Choice_combo", "Choice_radio", "Choices_check"]


def _index(options: list[Any], value: Any, owner: QWidget) -> int:
    """후보 안 자리.

    Raises:
        ValueError: 후보에 없는 값일 때.
    """
    if value not in options:
        raise ValueError(f"{type(owner).__name__}: {value!r} not in options {options}")
    return options.index(value)


def _at(options: list[Any], at: int, owner: QWidget) -> int:
    """후보 번호 확인.

    Raises:
        ValueError: 후보 밖 번호일 때.
    """
    if not 0 <= at < len(options):
        raise ValueError(f"{type(owner).__name__}: index {at} out of range - {len(options)} options")
    return at


def _fallback_one(options: list[Any], default: Any, default_at: int | None,
                  owner: QWidget) -> int:
    """하나 고르기의 기본 번호.

    Raises:
        ValueError: 기본을 둘 다 주거나 둘 다 안 줄 때, 후보 밖일 때.
    """
    if (default is None) == (default_at is None):
        raise ValueError(f"{type(owner).__name__}: give exactly one of default / default_at")
    return (_index(options, default, owner) if default_at is None
            else _at(options, default_at, owner))


def _fallback_many(options: list[Any], default: list[Any] | None,
                   default_at: list[int] | None, owner: QWidget) -> set[int]:
    """여럿 고르기의 기본 번호들. 둘 다 안 주면 안 고름.

    Raises:
        ValueError: 기본을 둘 다 줄 때, 후보 밖일 때.
    """
    if default is not None and default_at is not None:
        raise ValueError(f"{type(owner).__name__}: give at most one of default / default_at")
    if default_at is not None:
        return {_at(options, _a, owner) for _a in default_at}
    return {_index(options, _v, owner) for _v in default or []}


class _Button_group(QWidget):
    """후보마다 버튼 하나를 한 줄로. 사람의 고름은 `idClicked` 하나.

    Attributes:
        value_changed: 새 값
    """

    value_changed = Signal(object)

    def __init__(self, options: list[Any], button: type[QAbstractButton], exclusive: bool,
                 vertical: bool, parent: QWidget | None) -> None:
        """Args:
        options: 후보. 차례가 곧 보이는 차례.
        button: 후보마다 지을 버튼 클래스.
        exclusive: 하나만 눌리나.
        vertical: 세로 줄. 거짓이면 가로.
        parent: 부모 위젯.

        Raises:
            TypeError: `vertical` 이 bool 이 아닐 때.
        """
        if not isinstance(vertical, bool):
            raise TypeError(f"vertical must be bool - got {vertical!r}")
        super().__init__(parent)
        self._options = list(options)
        _lay = QBoxLayout(QBoxLayout.Direction.TopToBottom if vertical
                          else QBoxLayout.Direction.LeftToRight, self)
        _lay.setContentsMargins(0, 0, 0, 0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(exclusive)
        for _at_, _o in enumerate(self._options):
            _b = button(str(_o))
            self._group.addButton(_b, _at_)
            _lay.addWidget(_b)
        self._group.idClicked.connect(self._on_changed)

    def _on_changed(self, _id: int) -> None:
        self.value_changed.emit(self.value())

    def _check(self, picked: set[int]) -> None:
        """그 번호들만 누름. 버튼 신호는 안 씀 - `idClicked` 는 사람만 냄."""
        for _a in range(len(self._options)):
            self._group.button(_a).setChecked(_a in picked)


class Choice_radio(_Button_group):
    """후보 중 하나 - 라디오 버튼 줄."""

    def __init__(self, options: list[Any], default: Any = None, default_at: int | None = None,
                 vertical: bool = False, parent: QWidget | None = None) -> None:
        """Args:
        options: 후보. 차례가 곧 보이는 차례.
        default: 기본 후보. 처음 값, None 이 오면 돌아갈 값.
        default_at: 기본 후보 번호. `default` 대신.
        vertical: 세로 줄. 거짓이면 가로.
        parent: 부모 위젯.
        """
        super().__init__(options, QRadioButton, True, vertical, parent)
        self._fallback = _fallback_one(self._options, default, default_at, self)
        self.set_value(None)

    def value(self) -> Any:
        return self._options[self._group.checkedId()]

    def set_value(self, value) -> None:
        self._check({self._fallback if value is None
                     else _index(self._options, value, self)})


class Choices_check(_Button_group):
    """후보 중 여럿 - 체크박스 줄. 값은 고른 후보, 후보 차례대로."""

    def __init__(self, options: list[Any], default: list[Any] | None = None,
                 default_at: list[int] | None = None, vertical: bool = False,
                 parent: QWidget | None = None) -> None:
        """Args:
        options: 후보. 차례가 곧 보이는 차례.
        default: 기본 고른 후보들. 처음 값, None 이 오면 돌아갈 값. 둘 다 안 주면 안 고름.
        default_at: 기본 고른 후보 번호들. `default` 대신.
        vertical: 세로 줄. 거짓이면 가로.
        parent: 부모 위젯.
        """
        super().__init__(options, QCheckBox, False, vertical, parent)
        self._fallback = _fallback_many(self._options, default, default_at, self)
        self.set_value(None)

    def value(self) -> list[Any]:
        return [_o for _a, _o in enumerate(self._options)
                if self._group.button(_a).isChecked()]

    def set_value(self, value) -> None:
        self._check(self._fallback if value is None
                    else {_index(self._options, _v, self) for _v in value})


class Choice_combo(QComboBox):
    """후보 중 하나 - 펼침 목록.

    Attributes:
        value_changed: 고른 후보
    """

    value_changed = Signal(object)

    def __init__(self, options: list[Any], default: Any = None, default_at: int | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        options: 후보. 차례가 곧 보이는 차례.
        default: 기본 후보. 처음 값, None 이 오면 돌아갈 값.
        default_at: 기본 후보 번호. `default` 대신.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._options = list(options)
        self.addItems([str(_o) for _o in self._options])
        self._fallback = _fallback_one(self._options, default, default_at, self)
        self.set_value(None)
        self.currentIndexChanged.connect(self._on_changed)

    def _on_changed(self, _at_: int) -> None:
        self.value_changed.emit(self.value())

    def value(self) -> Any:
        return self._options[self.currentIndex()]

    def set_value(self, value) -> None:
        self.blockSignals(True)
        self.setCurrentIndex(self._fallback if value is None
                             else _index(self._options, value, self))
        self.blockSignals(False)
