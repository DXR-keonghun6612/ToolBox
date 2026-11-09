"""후보에서 하나 고르는 창 - 검색 필터 + 목록.

정본 params 의 id_map class 후보를 필터로 좁혀 하나 고른다. 편집형 콤보로는 수백 개를 훑기 어려워
별도 창으로 뺐다 — 다중선택 재배정에서 "선택한 sample 들 → 이 class 로" 의 대상을 정한다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ._dialog import Pop_dialog


class Search_picker(Pop_dialog):
    """class 후보 목록 + 검색 필터. ``exec()`` 후 ``selected()`` 로 고른 **class_id** (취소·미선택이면 None).

    **보여주는 건 이름, 돌려주는 건 번호다** — 저장되는 값이 번호라서다(이름은 id_map 이 개정하면 바뀐다).
    """

    def __init__(self, choices: dict[str, str], title: str = "class 재배정 — 대상 선택",
                 parent=None) -> None:
        """Args:
        choices: 후보 ``{표시 이름: class_id}`` — 값이 문자열인 건 저장 표현이 그래서다.
        title:   창 제목 — **무엇을 고르는 자리인지는 부르는 쪽이 안다**(재배정 대상 / 병합 생존자 …).
        """
        super().__init__(title, size=(360, 500), parent=parent)
        self._chosen: str | None = None
        # 번호순 — 값이 문자열이라 그대로 정렬하면 ``"100" < "2"`` 다.
        self._all = sorted(choices.items(),
                           key=lambda _kv: (int(_kv[1]) if str(_kv[1]).lstrip("-").isdigit()
                                            else 1 << 30, _kv[0]))
        self._build()
        self._populate("")

    def _build(self) -> None:
        _w = QWidget()
        _l = QVBoxLayout(_w)
        _l.setContentsMargins(0, 0, 0, 0)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("class 검색…")
        self._filter.textChanged.connect(self._populate)
        _l.addWidget(self._filter)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _it: self._accept())
        _l.addWidget(self._list, stretch=1)
        self._set_body(_w)
        self._bottom_bar(buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                         on_accept=self._accept, on_reject=self.reject)

    def _populate(self, text: str) -> None:
        _t = text.strip().lower()
        self._list.clear()
        for _name, _cid in self._all:
            if _t in _name.lower():
                _item = QListWidgetItem(_name)
                _item.setData(Qt.UserRole, _cid)      # 표시는 이름, 값은 번호
                self._list.addItem(_item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _accept(self) -> None:
        _it = self._list.currentItem()
        self._chosen = _it.data(Qt.UserRole) if _it is not None else None
        self.accept()

    def selected(self) -> str | None:
        return self._chosen
