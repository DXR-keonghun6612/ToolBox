"""tree 보기 - JSON 꼴 문서 하나를 key, 값 두 칸으로. `QTreeWidget` 바로 상속, model 없음 - 문서 하나라 행이 적음.

- dict 는 자식 노드, 목록은 순번 0, 1, 2 를 key 로 원소마다 자식 노드. 값 칸에 원소 수 - dict `{n}`, 목록 `[n]`
- 깊이 `depth` 까지 펼침. 맨 위 키가 1 단. 그보다 깊은 dict, 목록은 원소 수만
- 목록 안의 목록은 값 칸에 한 줄 - 처음 셋, 줄임표, 마지막 하나
- 원소가 모두 dict 인 목록은 안 펼침 - 원소 수만
- `open` 에 적힌 키는 자료형과 상관없이 안 펼침. 그 노드를 더블클릭하면 `open_requested(영역, 값)`. 영역에 넘기는 것은 page
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

__all__ = ["Tree_view"]

#: 노드가 드는 값의 자리 - 더블클릭이 보낼 것.
_VALUE = Qt.ItemDataRole.UserRole
#: 노드가 여는 영역 이름의 자리. 없으면 None.
_REGION = Qt.ItemDataRole.UserRole + 1


def _count(value: dict | list) -> str:
    """원소 수 표기 - dict `{n}`, 목록 `[n]`."""
    return f"{{{len(value)}}}" if isinstance(value, dict) else f"[{len(value)}]"


def _cell(value: Any) -> str:
    """한 줄 요약 안의 원소 하나. 안쪽 dict, 목록은 원소 수."""
    return _count(value) if isinstance(value, (dict, list)) else str(value)


def _line(values: list) -> str:
    """목록 하나를 한 줄로 - 넷을 넘으면 처음 셋, 줄임표, 마지막 하나."""
    _parts = [_cell(_v) for _v in values]
    if len(_parts) > 4:
        _parts = _parts[:3] + ["..."] + _parts[-1:]
    return f"[{', '.join(_parts)}]"


def _records(value: list) -> bool:
    """원소가 모두 dict 인 목록인가. 빈 목록은 아님."""
    return bool(value) and all(isinstance(_v, dict) for _v in value)


class Tree_view(QTreeWidget):
    """JSON 꼴 문서 하나.

    Attributes:
        open_requested: `(영역 이름, 그 노드의 값)`
    """

    open_requested = Signal(str, object)

    def __init__(self, depth: int, open: dict[str, str] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        depth: 펼치는 깊이. 맨 위 키가 1 단.
        open: `문서 키 -> 영역 이름`. 그 키의 노드는 안 펼치고 더블클릭에 엶.
        parent: 부모 위젯.

        Raises:
            ValueError: `depth` 가 1 보다 작을 때.
            TypeError: `depth` 가 int 가 아닐 때, `open` 의 키 · 영역이 글자가 아닐 때.
        """
        if type(depth) is not int:
            raise TypeError(f"depth must be int - got {depth!r}")
        if depth < 1:
            raise ValueError(f"depth must be >= 1 - got {depth}")
        _open = dict(open or {})
        for _k, _v in _open.items():
            if not isinstance(_k, str) or not isinstance(_v, str):
                raise TypeError(f"open must map str doc key -> str region - got {_k!r}: {_v!r}")
        super().__init__(parent)
        self._depth = depth
        self._open = _open
        self.setHeaderLabels(["key", "값"])
        self.itemDoubleClicked.connect(self._on_double)

    def regions(self) -> set[str]:
        """`open_requested` 가 낼 수 있는 영역 이름 - `open` 의 값."""
        return set(self._open.values())

    def set_doc(self, doc: dict) -> None:
        """문서를 갈아끼움. 깊이까지 펼친 채로.

        Raises:
            TypeError: `doc` 이 dict 가 아닐 때.
        """
        if not isinstance(doc, dict):
            raise TypeError(f"doc must be dict - got {type(doc).__name__}")
        self.clear()
        for _k, _v in doc.items():
            self._add(self.invisibleRootItem(), _k, _v, 1)
        self.expandAll()

    def _add(self, parent: QTreeWidgetItem, key: Any, value: Any, level: int,
             in_list: bool = False) -> None:
        """노드 하나와 그 아래.

        Args:
            parent: 붙일 노드.
            key: 문서 키 또는 순번.
            value: 그 값.
            level: 이 노드의 단.
            in_list: 부모가 목록인가 - 목록 안의 목록은 한 줄로 끝남.
        """
        _inline = in_list and isinstance(value, list)
        _item = QTreeWidgetItem(parent, [str(key), _line(value) if _inline else self._text(value)])
        _item.setData(0, _VALUE, value)
        if not in_list and key in self._open:
            _item.setData(0, _REGION, self._open[key])
            return
        if _inline or level >= self._depth:
            return
        if isinstance(value, dict):
            for _k, _v in value.items():
                self._add(_item, _k, _v, level + 1)
        elif isinstance(value, list) and not _records(value):
            for _at, _v in enumerate(value):
                self._add(_item, _at, _v, level + 1, in_list=True)

    @staticmethod
    def _text(value: Any) -> str:
        """값 칸 글자. dict, 목록은 원소 수, None 은 빈 글자."""
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return _count(value)
        return str(value)

    def _on_double(self, item: QTreeWidgetItem, _column: int) -> None:
        _region = item.data(0, _REGION)
        if _region is not None:
            self.open_requested.emit(_region, item.data(0, _VALUE))
