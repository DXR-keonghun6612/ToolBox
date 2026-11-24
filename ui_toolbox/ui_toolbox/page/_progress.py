"""진행 화면 - 진행 막대, 상태 줄, 로그 칸, 멈춤, 닫기. 작업을 모름 - 잇는 쪽이 `begin`, `report`, `line`, `end` 를 부름.

공개 메서드는 어느 스레드에서 불러도 됨 - 안에서 신호를 내고, 화면은 popup 이 사는 GUI 스레드에서 바뀜.
멈춤 버튼은 `stop_requested` 신호만 - 무엇을 멈출지는 잇는 쪽.
`begin` 에 기록 파일을 주면 따라 읽음 - python_toolbox 기록의 JSON 줄(`EVENT_FILE`)마다 로그 칸 한 줄,
launcher 의 `job ended` 줄 수 / `total` 이 진행. 읽기는 `begin` 때의 파일 끝부터, `end` 때 남은 줄까지.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
from python_toolbox.run.launcher import LAUNCHER_LOGGER

from .. import component
from ._popup import Popup

__all__ = ["Progress_popup"]


class Progress_popup(Popup):
    """진행 하나를 보이는 popup. `begin` 부터 `end` 까지가 한 번.

    Attributes:
        bar: 진행 막대
        state: 상태 줄 - 지난 시간, 진행, 마지막 줄
        log: 로그 칸 - `line` 으로 받은 줄
        stop_requested: 멈춤 버튼을 누름
    """

    #: 상태 줄을 고치는 간격(ms).
    TICK_MS = 1000
    #: 기록 파일을 다시 읽는 간격(ms).
    FOLLOW_MS = 200

    stop_requested = Signal()
    _begun = Signal(object)
    _reported = Signal(int, int, str)
    _lined = Signal(str)
    _ended = Signal(bool, str)

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
        self._follow = QTimer(self)
        self._follow.setInterval(self.FOLLOW_MS)
        self._follow.timeout.connect(self._read_log)
        self._log_file: Path | None = None
        self._offset = 0
        self._ended_jobs = 0
        self._begun.connect(self._on_begin)
        self._reported.connect(self._on_report)
        self._lined.connect(self._on_line)
        self._ended.connect(self._on_end)

        self._running = False
        self._locked: tuple[QWidget, ...] = ()
        self._started = 0.0
        self._last = ""
        self._done = self._total = 0
        self.state.setText("대기")
        self._stop.setEnabled(False)

    @property
    def running(self) -> bool:
        """`begin` 뒤 아직 `end` 가 안 옴."""
        return self._running

    def begin(self, lock: tuple[QWidget, ...] = (), log_file: str | Path | None = None, total: int = 0) -> None:
        """띄우고 시작. 로그와 진행을 비우고, `lock` 은 `end` 까지 잠금.

        Args:
            lock: `end` 까지 잠글 위젯.
            log_file: 따라 읽을 기록 파일(`EVENT_FILE`). 비면 받은 `line`, `report` 만 보임.
            total: 진행의 전체 - launcher 의 job 수. `log_file` 이 있을 때.

        Raises:
            RuntimeError: 앞의 진행이 아직 안 끝남.
        """
        if self._running:
            raise RuntimeError("progress already running in this popup")
        self._running = True
        _file = Path(log_file) if log_file is not None else None
        _offset = _file.stat().st_size if _file is not None and _file.is_file() else 0
        self._begun.emit((tuple(lock), _file, _offset, total))

    def report(self, done: int, total: int, text: str = "") -> None:
        """진행. `total <= 0` 은 전체를 모름. `text` 가 있으면 상태 줄의 마지막 줄로."""
        self._reported.emit(done, total, text)

    def line(self, text: str) -> None:
        """로그 칸에 한 줄."""
        self._lined.emit(text)

    def end(self, ok: bool, summary: str = "") -> None:
        """끝. 성공 / 실패와 요약을 상태 줄에, 잠금 풂, 닫기 켬."""
        self._ended.emit(ok, summary)

    # ── GUI 스레드 ────────────────────────────────────────────────────────────
    def _on_begin(self, begun: tuple[tuple[QWidget, ...], Path | None, int, int]) -> None:
        lock, self._log_file, self._offset, _total = begun
        self.log.clear()
        self._last = ""
        self._done, self._total = 0, _total
        self._ended_jobs = 0
        self._locked = lock
        for _w in self._locked:
            _w.setEnabled(False)
        self._stop.setEnabled(True)
        self._close.setEnabled(False)
        self._started = time.monotonic()
        self.bar.report(0, self._total, "시작")
        self.show()
        self._tick.start()
        if self._log_file is not None:
            self._follow.start()
        self._show_state()

    def _on_report(self, done: int, total: int, text: str) -> None:
        self._done, self._total = done, total
        self.bar.report(done, total)
        if text:
            self._last = text

    def _on_line(self, text: str) -> None:
        self.log.appendPlainText(text)
        self._last = text

    def _on_end(self, ok: bool, summary: str) -> None:
        if self._log_file is not None:
            self._follow.stop()
            self._read_log()
            self._log_file = None
        self._tick.stop()
        for _w in self._locked:
            _w.setEnabled(True)
        self._locked = ()
        if self._total <= 0:
            self.bar.report(1, 1)
        _tail = f" · {summary}" if summary else ""
        self.state.setText(f"끝 - {'성공' if ok else '실패'} · {self._progress_text()}{_tail}")
        self._stop.setEnabled(False)
        self._close.setEnabled(True)
        self._running = False

    def _read_log(self) -> None:
        """기록 파일의 새 줄을 로그 칸으로, launcher 의 `job ended` 를 진행으로. 다 쓰인 줄까지만 - 나머지는 다음 번에."""
        if self._log_file is None or not self._log_file.is_file():
            return
        with self._log_file.open("rb") as _f:
            _f.seek(self._offset)
            _chunk = _f.read()
        _cut = _chunk.rfind(b"\n") + 1
        self._offset += _cut
        for _raw in _chunk[:_cut].decode("utf-8").splitlines():
            self._on_record(json.loads(_raw))

    def _on_record(self, record: dict[str, Any]) -> None:
        self._on_line(f"{record.get('time', '')} {record.get('level', '')} {record.get('name', '')} - "
                      f"{record.get('message', '')}")
        if record.get("name") == LAUNCHER_LOGGER and record.get("message") == "job ended":
            self._ended_jobs += 1
            self._on_report(self._ended_jobs, self._total, f"{record.get('job', '')} ended")

    # ── 안 ────────────────────────────────────────────────────────────────────
    def _progress_text(self) -> str:
        return f"{self._done} / {self._total}" if self._total > 0 else f"{self._done}"

    def _show_state(self) -> None:
        _spent = time.monotonic() - self._started
        self.state.setText(f"도는 중 · {_spent / 60:.0f}분 {_spent % 60:02.0f}초 · {self._progress_text()} · "
                           f"{self._last[:100]}")

    def _on_stop(self) -> None:
        self._stop.setEnabled(False)
        self.stop_requested.emit()
