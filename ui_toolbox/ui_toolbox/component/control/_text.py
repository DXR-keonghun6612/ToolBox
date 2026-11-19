"""글자 control - str 의 text, path. list[str] 의 구분자 text, paths.

칸이 비면 값은 None. `value_changed` 는 입력을 마칠 때 - 한 자마다 안 냄. 글자가 그대로면 안 냄(초점만 옮겨도
`editingFinished` 가 남).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QToolButton, QWidget

__all__ = ["List_text", "Path_text", "Paths_text", "Str_text"]


def _join(values: list | None, separator: str) -> str:
    """목록 -> 칸 글자. None 은 빈 글자."""
    return "" if values is None else separator.join(str(_v) for _v in values)


def _split(text: str, separator: str) -> list[str] | None:
    """칸 글자 -> 목록. 빈 조각은 버림, 남는 것이 없으면 None."""
    _parts = [_s.strip() for _s in text.split(separator) if _s.strip()]
    return _parts or None


class _Line_text(QLineEdit):
    """한 줄 입력. 입력을 마칠 때 글자가 바뀌었으면 `value_changed`. 글자 <-> 값 변환은 서브클래스."""

    value_changed = Signal(object)

    def __init__(self, placeholder: str, parent: QWidget | None) -> None:
        super().__init__(parent)
        self._last = ""
        self.setPlaceholderText(placeholder)
        self.editingFinished.connect(self._commit)

    def _commit(self) -> None:
        if self.text() == self._last:
            return
        self._last = self.text()
        self.value_changed.emit(self.value())

    def _show(self, text: str) -> None:
        """칸 글자를 신호 없이 바꿈."""
        self._last = text
        self.blockSignals(True)
        self.setText(text)
        self.blockSignals(False)


class Str_text(_Line_text):
    """글자 하나 - 한 줄 입력.

    Attributes:
        value_changed: 새 글자 또는 None
    """

    def __init__(self, default: str | None = None, placeholder: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        default: 초기값.
        placeholder: 빈 칸에 비쳐 보일 문구.
        parent: 부모 위젯.
        """
        super().__init__(placeholder, parent)
        self.set_value(default)

    def value(self) -> str | None:
        return self.text() or None

    def set_value(self, value) -> None:
        self._show("" if value is None else str(value))


class List_text(_Line_text):
    """글자 목록 - 한 줄 입력을 구분자로 가름.

    Attributes:
        value_changed: 새 목록 또는 None
    """

    def __init__(self, default: list[str] | None = None, separator: str = ",",
                 parent: QWidget | None = None) -> None:
        """Args:
        default: 초기값.
        separator: 조각을 가르는 글자.
        parent: 부모 위젯.
        """
        self._separator = separator
        super().__init__("", parent)
        self.set_value(default)

    def value(self) -> list[str] | None:
        return _split(self.text(), self._separator)

    def set_value(self, value) -> None:
        self._show(_join(value, f"{self._separator} "))


class _Browse_text(QWidget):
    """한 줄 입력 + 찾기 버튼. 손으로 적거나 대화상자로 고름.

    대화상자는 마지막에 쓴 경로의 폴더에서 열림 - 그 폴더를 state 로 듦.
    대화상자와 글자 <-> 값 변환은 서브클래스.
    """

    def __init__(self, tip: str, placeholder: str, parent: QWidget | None) -> None:
        """Args:
        tip: 찾기 버튼 툴팁.
        placeholder: 빈 칸에 비쳐 보일 문구.
        parent: 부모 위젯.
        """
        super().__init__(parent)
        self._last = ""
        self._start = ""
        _lay = QHBoxLayout(self)
        _lay.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        _lay.addWidget(self._edit, stretch=1)
        _browse = QToolButton()
        _browse.setText("📁")
        _browse.setToolTip(tip)
        _lay.addWidget(_browse)

        _browse.clicked.connect(self._browse)
        self._edit.editingFinished.connect(self._commit)

    def _pick(self) -> str:
        """대화상자로 고른 것의 칸 글자. 취소면 빈 글자. `self._start` 에서 엶."""
        raise NotImplementedError(f"{type(self).__name__}._pick")

    def _paths(self) -> list[str]:
        """지금 칸의 경로들."""
        raise NotImplementedError(f"{type(self).__name__}._paths")

    def _remember(self) -> None:
        """대화상자 시작 폴더를 지금 칸의 첫 경로에서. 칸이 비면 그대로."""
        _paths = self._paths()
        if _paths:
            _first = _paths[0]
            self._start = _first if os.path.isdir(_first) else os.path.dirname(_first)

    def _browse(self) -> None:
        _picked = self._pick()
        if _picked:
            self._edit.setText(_picked)
            self._commit()

    def _commit(self) -> None:
        # editingFinished 는 초점만 옮겨도 남 - 글자가 그대로면 안 냄
        _text = self._edit.text()
        if _text == self._last:
            return
        self._last = _text
        self._remember()
        self.value_changed.emit(self.value())

    def _show(self, text: str) -> None:
        """칸 글자를 신호 없이 바꿈."""
        self._last = text
        self._edit.blockSignals(True)
        self._edit.setText(text)
        self._edit.blockSignals(False)
        self._remember()


class Path_text(_Browse_text):
    """경로 하나 - 있는 디렉터리 고르기, 있는 파일 하나 열기.

    Attributes:
        value_changed: 새 경로 또는 None
    """

    value_changed = Signal(object)

    def __init__(self, default: str | None = None, mode: str = "dir",
                 file_filter: str = "", placeholder: str = "",
                 parent: QWidget | None = None) -> None:
        """Args:
        default: 초기값.
        mode: `'dir'` 이면 디렉터리, `'file'` 이면 파일 하나.
        file_filter: `mode == 'file'` 일 때 대화상자 필터 (`"YAML (*.yaml *.yml)"`).
        placeholder: 빈 칸에 비쳐 보일 문구.
        parent: 부모 위젯.

        Raises:
            ValueError: `mode` 가 `'dir'`, `'file'` 밖일 때.
        """
        if mode not in ("dir", "file"):
            raise ValueError(f"mode must be 'dir' or 'file' - got {mode!r}")
        self._mode = mode
        self._filter = file_filter
        super().__init__("디렉터리 선택" if mode == "dir" else "파일 선택", placeholder, parent)
        self.set_value(default)

    def _pick(self) -> str:
        if self._mode == "file":
            return QFileDialog.getOpenFileName(
                self, "파일 선택", self._start, self._filter)[0]
        return QFileDialog.getExistingDirectory(self, "디렉터리 선택", self._start)

    def _paths(self) -> list[str]:
        _v = self.value()
        return [] if _v is None else [_v]

    def value(self) -> str | None:
        return self._edit.text().strip() or None

    def set_value(self, value) -> None:
        self._show("" if value is None else str(value))


class Paths_text(_Browse_text):
    """경로 여럿 - 있는 파일 여럿 열기. 칸에는 `os.pathsep` 으로 이어 적음.

    Attributes:
        value_changed: 새 경로 목록 또는 None
    """

    value_changed = Signal(object)

    def __init__(self, default: list[str] | None = None, file_filter: str = "",
                 placeholder: str = "", parent: QWidget | None = None) -> None:
        """Args:
        default: 초기값.
        file_filter: 대화상자 필터 (`"YAML (*.yaml *.yml)"`).
        placeholder: 빈 칸에 비쳐 보일 문구.
        parent: 부모 위젯.
        """
        self._filter = file_filter
        super().__init__("파일 여럿 선택", placeholder, parent)
        self.set_value(default)

    def _pick(self) -> str:
        return os.pathsep.join(QFileDialog.getOpenFileNames(
            self, "파일 여럿 선택", self._start, self._filter)[0])

    def _paths(self) -> list[str]:
        return self.value() or []

    def value(self) -> list[str] | None:
        return _split(self._edit.text(), os.pathsep)

    def set_value(self, value) -> None:
        self._show(_join(value, os.pathsep))
