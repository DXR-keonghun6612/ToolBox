"""popup - main 위에 뜨는 창. 축은 둘, 서로 독립.

- `modal` : 부모를 막나 - `open` 이 `exec` / `show`
- `result` : 확인 / 취소 줄과 `accepted` · `rejected`. 값은 연 쪽이 key 경로로 읽음
- 본문은 `body` - build 가 배치를 걺. 확인 / 취소 줄은 그 아래
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

__all__ = ["Popup"]


class Popup(QDialog):
    """popup 하나.

    Attributes:
        body: 본문 자리 - build 가 배치를 걺
    """

    def __init__(self, modal: bool = False, result: bool = False, size: list[int] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        modal: 부모를 막나.
        result: 확인 / 취소 줄을 두나.
        size: 처음 크기 `(폭, 높이)`. 비면 Qt 기본.
        parent: 부모 위젯.

        Raises:
            TypeError: `modal`, `result` 가 bool 이 아닐 때.
            ValueError: `size` 가 둘이 아닐 때.
        """
        for _name, _v in (("modal", modal), ("result", result)):
            if not isinstance(_v, bool):
                raise TypeError(f"{_name} must be bool - got {_v!r}")
        if size is not None and len(size) != 2:
            raise ValueError(f"size must be (width, height) - got {size!r}")
        super().__init__(parent)
        if size is not None:
            self.resize(*size)
        self._blocking = modal
        self.body = QWidget()
        _lay = QVBoxLayout(self)
        _lay.addWidget(self.body, stretch=1)
        if result:
            _row = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            _row.accepted.connect(self.accept)
            _row.rejected.connect(self.reject)
            _lay.addWidget(_row)

    def is_blocking(self) -> bool:
        """부모를 막는 popup 인가."""
        return self._blocking

    def open(self) -> None:
        """띄움. modal 이면 닫힐 때까지 막음 - 결과는 `accepted` · `rejected`."""
        if self._blocking:
            self.exec()
            return
        self.show()
