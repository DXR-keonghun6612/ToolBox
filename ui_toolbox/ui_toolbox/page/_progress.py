"""작업 화면 - 작업의 진행을 GUI 스레드로 넘기고 보여 줌. 일을 돌리는 것은 작업(python_toolbox `project.job`).

작업의 계약 - `on(event, fn)`, `start()`, `stop()`, `running`. event 는 `start` `()`, `progress` `(done, total, text)`,
`line` `(text)`, `finish` `(ok, payload)`. 콜백은 일이 도는 스레드에서 옴 - 여기서 Qt 신호로 바꿔 GUI 스레드로.

- `Job_signals` - 작업 하나의 콜백 -> Qt 신호. 막대만 잇는 곳(제 화면의 `Progress_bar`)도 이것
- `Job_popup` - 진행 막대, 상태 줄, 로그, 멈춤, 닫기. 닫기는 끝난 뒤에만. 도는 동안 잠글 위젯을 받음
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from .. import component
from ._popup import Popup

__all__ = ["Job_popup", "Job_signals"]

#: 작업이 내는 event.
EVENTS = ("start", "progress", "line", "finish")


class Job_signals(QObject):
    """작업 하나의 콜백을 Qt 신호로. 이 객체가 GUI 스레드에 있으니 받는 쪽은 GUI 스레드에서 불림.

    Attributes:
        started: 시작
        progress: `(done, total, text)` - `total <= 0` 은 모름
        line: 출력 한 줄
        finished: `(ok, payload)`
    """

    started  = Signal()
    progress = Signal(int, int, str)
    line     = Signal(str)
    finished = Signal(bool, object)

    def __init__(self, job: Any, parent: QObject | None = None) -> None:
        """Args:
        job: 작업 - `on(event, fn)` 이 있는 것.
        parent: 부모 객체.
        """
        super().__init__(parent)
        self.job = job
        job.on("start", self.started.emit)
        job.on("progress", lambda done, total, text="": self.progress.emit(done, total, text))
        job.on("line", self.line.emit)
        job.on("finish", self.finished.emit)


class Job_popup(Popup):
    """작업 하나를 보이는 popup. `run` 마다 작업 하나.

    Attributes:
        bar: 진행 막대
        state: 상태 줄 - 지난 시간, 진행, 마지막 줄
        log: 출력 줄
    """

    #: 상태 줄을 고치는 간격(ms).
    TICK_MS = 1000

    def __init__(self, modal: bool = False, size: list[int] | None = None, parent: QWidget | None = None) -> None:
        """Args:
        modal: 부모를 막나.
        size: 처음 크기 `(폭, 높이)`. 비면 Qt 기본.
        parent: 부모 위젯.
        """
        super().__init__(modal=modal, result=False, size=size, parent=parent)
        self.bar = component.REGISTRY.Get("Progress_bar")()
        self.state = QLabel()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self._stop = QPushButton("멈춤")
        self._close = QPushButton("닫기")
        self._stop.clicked.connect(self._on_stop)
        self._close.clicked.connect(self.close)
        _row = QHBoxLayout()
        _row.addStretch(1)
        _row.addWidget(self._stop)
        _row.addWidget(self._close)
        _lay = QVBoxLayout(self.body)
        _lay.setContentsMargins(0, 0, 0, 0)
        for _w in (self.bar, self.state, self.log):
            _lay.addWidget(_w, stretch=1 if _w is self.log else 0)
        _lay.addLayout(_row)

        self._tick = QTimer(self)
        self._tick.setInterval(self.TICK_MS)
        self._tick.timeout.connect(self._show_state)
        self._signals: Job_signals | None = None
        self._locked: tuple[QWidget, ...] = ()
        self._started = 0.0
        self._last = ""
        self._done = self._total = 0
        self._idle()

    def run(self, job: Any, lock: tuple[QWidget, ...] = ()) -> None:
        """작업을 잇고 띄우고 시작. `lock` 은 끝날 때까지 잠금.

        Raises:
            RuntimeError: 앞의 작업이 아직 돌 때.
        """
        if self._signals is not None and self._signals.job.running:
            raise RuntimeError("a job is still running in this popup")
        self.log.clear()
        self._last = ""
        self._done = self._total = 0
        self._signals = Job_signals(job, self)
        self._signals.started.connect(self._on_started)
        self._signals.progress.connect(self._on_progress)
        self._signals.line.connect(self._on_line)
        self._signals.finished.connect(self._on_finished)
        self._locked = tuple(lock)
        for _w in self._locked:
            _w.setEnabled(False)
        self._stop.setEnabled(True)
        self._close.setEnabled(False)
        self.show()
        job.start()

    # ── 작업의 신호 ───────────────────────────────────────────────────────────
    def _on_started(self) -> None:
        self._started = time.monotonic()
        self.bar.report(0, 0, "시작")
        self._tick.start()
        self._show_state()

    def _on_progress(self, done: int, total: int, text: str) -> None:
        self._done, self._total = done, total
        self.bar.report(done, total)

    def _on_line(self, text: str) -> None:
        self.log.appendPlainText(text)
        self._last = text

    def _on_finished(self, ok: bool, payload: object) -> None:
        self._tick.stop()
        for _w in self._locked:
            _w.setEnabled(True)
        self._locked = ()
        if self._total <= 0:
            self.bar.report(1, 1)
        self.state.setText(f"끝 - {'성공' if ok else '실패'} · {self._progress_text()} · {payload}")
        self._stop.setEnabled(False)
        self._close.setEnabled(True)

    # ── 안 ────────────────────────────────────────────────────────────────────
    def _idle(self) -> None:
        self.state.setText("대기")
        self._stop.setEnabled(False)
        self._close.setEnabled(True)

    def _progress_text(self) -> str:
        return f"{self._done} / {self._total}" if self._total > 0 else f"{self._done}"

    def _show_state(self) -> None:
        _spent = time.monotonic() - self._started
        self.state.setText(f"도는 중 · {_spent / 60:.0f}분 {_spent % 60:02.0f}초 · {self._progress_text()} · "
                           f"{self._last[:100]}")

    def _on_stop(self) -> None:
        if self._signals is not None:
            self._signals.job.stop()
