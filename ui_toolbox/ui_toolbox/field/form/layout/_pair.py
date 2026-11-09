"""key/value 쌍 목록 - layout 표현의 소비처.

칸이 둘로 고정이라 표로도 설 수 있지만, 행마다 파일 찾기 버튼이 붙어 layout 표현 쪽이 맞다.
중복 key 와 순서를 허용하므로 dict 이 아니라 쌍의 목록으로 왕복한다.

등록표에 자기를 올린다 - 위젯 층이 이 파일을 보면 방향이 거꾸로 선다.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QWidget

from ..._field import Field, Rows
from ..._item import Button
from ..widget import Button_bar, Register
from ._stack import Stack_view

KEY   = "key"
VALUE = "value"

_BROWSE = 0


class Pair_editor(Stack_view):
    """`(key, value)` 쌍을 행 단위로 편집. payload 는 쌍의 목록."""

    def __init__(self, title: str = "", kind: str = "", tip: str = "",
                 fields: list[Field] | None = None,
                 parent: QWidget | None = None) -> None:
        """편집기를 구성.

        Args:
            title: 맨 위 라벨. 빈 문자열이면 없음.
            kind: `'path'` 면 값 칸에 파일 찾기 버튼을 붙임.
            tip: 위젯 툴팁.
            fields: 두 칸의 선언. 없으면 기본 - 소비처가 폭 · 문구를 정할 자리.
            parent: 부모 위젯.
        """
        self._kind = kind
        super().__init__(
            Rows(fields or [Field(KEY, str), Field(VALUE, str)]),
            title=title, header=False, parent=parent)
        if tip:
            self.setToolTip(tip)

    def _extras(self, at: int) -> list[QWidget]:
        """행 끝 버튼 - 파일 찾기. 선언한 것만 붙음."""
        if self._kind != "path":
            return []
        _bar = Button_bar([Button("📁", "파일 찾기", value=_BROWSE)])
        _bar.fired.connect(lambda _what, _a=at: self._on_browse(_a))
        return [_bar]

    def _on_browse(self, at: int) -> None:
        """고른 경로를 값 칸에 적음. 취소면 그대로 둠."""
        _path, _ = QFileDialog.getOpenFileName(self, "파일 선택")
        if _path and self._data.set(at, VALUE, _path):
            self.refresh()
            self._emit()

    # ── public API ────────────────────────────────────────────────────────────
    def value(self) -> list[tuple[str, str]]:
        """지금 쌍들. key 가 빈 행은 뺌."""
        return [(str(_r.get(KEY, "")), str(_r.get(VALUE, "")))
                for _r in super().value() if str(_r.get(KEY, "")).strip()]

    def set_value(self, value) -> None:
        super().set_value([{KEY: str(_k), VALUE: str(_v)}
                           for _k, _v in (value or [])])

    def append_pair(self, key: str, value: str) -> None:
        """행 하나를 붙이고 알림."""
        self._data.append({KEY: key, VALUE: value})
        self.refresh()
        self._emit()


@Register("list_pair")
def _pairs(spec: Field, label: str) -> QWidget:
    """쌍 목록 칸의 자리."""
    _editor = Pair_editor(label, kind=spec.kind, tip=spec.tip)
    _editor.set_value(spec.default)
    return _editor
