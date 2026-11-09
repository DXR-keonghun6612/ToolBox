"""경로 한 칸 - 라벨 + 한 줄 입력 + 탐색 버튼.

값이 바뀌는 것과 그 자리를 다시 읽어 달라는 것은 다른 사건. 신호를 둘로 가름.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from .....style import LABEL, Mark, Now
from ...._value import Value


class Path_row(Value):
    """경로 하나를 받는 행. 탐색 버튼으로 고르거나 손으로 적음.

    Attributes:
        value_changed: 새 경로
        refresh: 같은 경로를 다시 읽어 달라는 요청. 값은 안 바뀜
    """

    value_changed = Signal(str)
    refresh = Signal()

    def __init__(self, label: str, placeholder: str = "", mode: str = "dir",
                 refresh: bool = False, file_filter: str = "", tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        label: 왼쪽 라벨. 비면 라벨 없이 값만.
        placeholder: 빈 칸에 비쳐 보일 문구.
        mode: `'dir'` 이면 디렉터리, `'file'` 이면 파일 고르기.
        refresh: 새로고침 버튼을 붙임. 눌리면 `refresh` 신호.
        file_filter: `mode == 'file'` 일 때 다이얼로그 필터 (`"YAML (*.yaml *.yml)"`).
        tooltip: 위젯 툴팁.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._mode = mode
        self._filter = file_filter
        self._last = ""

        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        _lay.setSpacing(Now()["gap"])
        if label:
            _lay.addWidget(Mark(QLabel(label), LABEL))

        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        _lay.addWidget(self._edit, stretch=1)

        _browse = QToolButton()
        _browse.setText("📁")
        _browse.setToolTip("디렉터리 선택" if mode == "dir" else "파일 선택")
        _lay.addWidget(_browse)

        if refresh:
            _reload = QToolButton()
            _reload.setText("↺")
            _reload.setToolTip("새로고침")
            _reload.clicked.connect(self.refresh)
            _lay.addWidget(_reload)

        if tooltip:
            self.setToolTip(tooltip)
        _browse.clicked.connect(self._browse)
        self._edit.editingFinished.connect(lambda: self._commit(self._edit.text()))

    def _browse(self) -> None:
        """다이얼로그로 고름. 취소면 그대로 둠."""
        if self._mode == "file":
            _picked, _ = QFileDialog.getOpenFileName(self, "파일 선택", "", self._filter)
        else:
            _picked = QFileDialog.getExistingDirectory(self, "디렉터리 선택")
        if _picked:
            self._edit.setText(_picked)
            self._commit(_picked)

    def _commit(self, path: str) -> None:
        """사람이 고쳤을 때의 후처리. 값이 그대로면 안 냄 - 초점만 옮겨도 불림."""
        if path == self._last:
            return
        self._last = path
        self.value_changed.emit(path)
        self.edited.emit()

    def value(self) -> str:
        return self._edit.text()

    def set_value(self, value) -> None:
        self._last = "" if value is None else str(value)
        self._edit.blockSignals(True)
        self._edit.setText(self._last)
        self._edit.blockSignals(False)
