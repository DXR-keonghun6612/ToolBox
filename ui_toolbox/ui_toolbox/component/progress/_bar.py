"""진행 막대 - 받은 수와 글자를 보이기만.

무엇이 도는지, 언제 시작 · 끝인지 모름 - 값은 page 가 줌.
"""

from __future__ import annotations

from PySide6.QtWidgets import QProgressBar, QWidget

__all__ = ["Progress_bar"]


class Progress_bar(QProgressBar):
    """수와 글자를 보이는 막대. 전체를 모르면 불확정 막대, 알면 채워지는 막대."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.report(0, 1)

    def report(self, done: int, total: int, text: str = "") -> None:
        """수와 글자를 보임.

        Args:
            done: 지금까지 처리한 수.
            total: 전체 수. `0` 이하면 아직 모름 - 불확정 막대, 처리한 수만 보임.
            text: 함께 보일 글자.
        """
        if total > 0:
            self.setRange(0, total)
            self.setValue(done)
            self.setFormat(f"{text} : %v / %m" if text else "%v / %m")
            return
        self.setRange(0, 0)                      # 불확정 - 전체를 아직 모름
        _count = f"({done})" if done else ""
        self.setFormat(" ".join(_p for _p in (text, _count) if _p))
