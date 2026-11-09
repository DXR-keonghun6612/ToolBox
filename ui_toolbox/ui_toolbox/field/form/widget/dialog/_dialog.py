"""팝아웃 다이얼로그 베이스 — 제목·크기·본문·하단 버튼바 골격 (순수 Qt)."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


class Pop_dialog(QDialog):
    """제목·크기·세로 레이아웃을 갖춘 팝아웃 다이얼로그 베이스.

    서브클래스는 ``_set_body(widget)`` 로 본문을, ``_bottom_bar(...)`` 로 하단 버튼줄을 깐다.
    """

    def __init__(self, title: str, *, size: tuple[int, int] | None = None,
                 parent: QWidget | None = None) -> None:
        """다이얼로그 골격을 만든다.

        Args:
            title: 창 제목.
            size: ``(w, h)`` 초기 크기 (None이면 Qt 기본).
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        if size is not None:
            self.resize(*size)
        self._lay = QVBoxLayout(self)

    def _set_body(self, widget: QWidget) -> None:
        """본문 위젯을 ``stretch=1`` 로 배치한다 (다이얼로그의 주 영역)."""
        self._lay.addWidget(widget, stretch=1)

    def _bottom_bar(
        self,
        *,
        left: Iterable[QWidget] = (),
        extra: Iterable[QWidget] = (),
        buttons: QDialogButtonBox.StandardButton = QDialogButtonBox.Close,
        on_accept=None,
        on_reject=None,
    ) -> QDialogButtonBox:
        """하단 버튼줄을 깐다 — ``[왼쪽 버튼…] (stretch) [extra 위젯…] [QDialogButtonBox]``.

        Args:
            left: 좌측에 둘 액션 버튼들(저장/불러오기 등).
            extra: 우측 박스 앞에 둘 위젯들(상태 라벨·실행 버튼 등).
            buttons: ``QDialogButtonBox`` 표준 버튼 플래그.
            on_accept: accepted 시그널 핸들러 (있으면 연결).
            on_reject: rejected 시그널 핸들러 (있으면 연결).

        Returns:
            만든 ``QDialogButtonBox`` (서브클래스가 추가 와이어링에 쓸 수 있게).
        """
        _row = QHBoxLayout()
        for _w in left:
            _row.addWidget(_w)
        _row.addStretch()
        for _w in extra:
            _row.addWidget(_w)
        _box = QDialogButtonBox(buttons)
        if on_accept is not None:
            _box.accepted.connect(on_accept)
        if on_reject is not None:
            _box.rejected.connect(on_reject)
        _row.addWidget(_box)
        self._lay.addLayout(_row)
        return _box
