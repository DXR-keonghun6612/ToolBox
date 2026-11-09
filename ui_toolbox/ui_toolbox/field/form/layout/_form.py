"""파라미터 폼 - 칸 선언 목록을 등록표가 짓는 위젯으로 세로로 쌓음."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ....style import Now
from ..._field import Field
from ..._value import Value
from ..widget import Build


class Config_form(QWidget):
    """칸 선언 목록으로 편집 폼을 지음. 값은 `get` · `load` 로 왕복.

    모르는 자료형은 조용히 안 넘기고 실패한다. 위젯이 안 생기면 그 칸은 `get()` 에서 빠져
    소비처가 기본값으로 돌아버린다 - 사람은 값을 넣었다고 믿는데. 그래서 자리가 빈 자료형은
    에러로 드러낸다: 등록표에 올리든지, 그 칸을 폼에 안 주든지 둘 중 하나를 하게.

    Attributes:
        params_changed: 사람이 어느 칸이든 고침.
    """

    params_changed = Signal()

    def __init__(self, specs: list[Field], parent=None) -> None:
        """Args:
        specs: 위젯을 만들 칸 선언 목록.

        Raises:
            TypeError: 등록표에 자리가 없는 칸이 있을 때.
        """
        super().__init__(parent)
        self._widgets: dict[str, Value] = {}

        _lay = QVBoxLayout(self)
        _lay.setSpacing(Now()["gap"])
        _lay.setContentsMargins(0, 0, 0, 0)
        _missing: list[Field] = []
        for _spec in specs:
            _w = Build(_spec)
            if _w is None:
                _missing.append(_spec)
                continue
            # payload 를 버려 계약의 신호에 자료형이 안 듦
            _w.edited.connect(self.params_changed)
            self._widgets[_spec.name] = _w
            _lay.addWidget(_w)
        if _missing:
            raise TypeError(
                "등록표에 자리가 없는 칸: "
                + ", ".join(f"{_s.name}: {_s.type}" for _s in _missing)
                + " - 위젯을 올리거나 그 칸을 빼세요 "
                  "(조용히 버리면 값이 안 실려 기본값으로 돕니다).")

    def get(self) -> dict[str, Any]:
        """지금 폼 값 - `{이름: 값}`."""
        return {_name: _w.value() for _name, _w in self._widgets.items()}

    def load(self, params: dict) -> None:
        """저장된 값으로 폼을 되돌림. 신호 안 냄, 폼에 없는 키는 무시."""
        for _name, _val in params.items():
            _w = self._widgets.get(_name)
            if _w is not None:
                _w.set_value(_val)
