"""작업 화면 - 작업의 콜백을 GUI 스레드로, Job_popup 의 진행 · 로그 · 잠금 · 멈춤 · 끝, config 의 link.

작업은 python_toolbox `project.job` 의 계약 꼴을 흉내 낸 `_Fake` - 따로 도는 스레드에서 콜백.
"""

from __future__ import annotations

import threading

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QWidget

from ui_toolbox.page import Fill, Job_popup, Job_signals
from ui_toolbox.page._job import EVENTS


def _wait(ready, ms: int = 2000) -> None:
    """`ready()` 가 참이 될 때까지 이벤트를 돌림 - 다른 스레드의 신호가 GUI 스레드로 오게. 시간 안에 안 서면 실패."""
    for _ in range(ms // 10):
        if ready():
            return
        QTest.qWait(10)
    raise AssertionError("wait: condition not met in time")


class _Fake:
    """`on`, `start`, `stop`, `running` - 스레드에서 `steps` 만큼 줄과 진행을 내고 끝. `gate` 가 있으면 그것을 기다린 뒤 시작."""

    def __init__(self, steps: int, gate: threading.Event | None = None) -> None:
        self._subs: dict[str, list] = {_e: [] for _e in EVENTS}
        self._steps = steps
        self._gate = gate
        self.running = False
        self.stopped = False

    def on(self, event, fn) -> None:
        if event not in self._subs:
            raise KeyError(event)
        self._subs[event].append(fn)

    def _emit(self, event, *args) -> None:
        for _fn in self._subs[event]:
            _fn(*args)

    def start(self) -> None:
        self.running = True

        def _run():
            self._emit("start")
            if self._gate is not None:
                self._gate.wait(2)
            for _i in range(self._steps):
                if self.stopped:
                    break
                self._emit("line", f"ok {_i}")
                self._emit("progress", _i + 1, self._steps, f"ok {_i}")
            self.running = False
            self._emit("finish", not self.stopped, 0)

        threading.Thread(target=_run).start()

    def stop(self) -> None:
        self.stopped = True


def test_job_signals_flow():
    # 단계 : 콜백 -> 신호, 받는 쪽은 GUI 스레드
    _job = _Fake(2)
    _signals = Job_signals(_job)
    _seen: list = []
    _signals.progress.connect(lambda d, t, s: _seen.append((d, t, threading.get_ident())))
    _signals.finished.connect(lambda ok, p: _seen.append(("finish", ok)))
    _job.start()
    _wait(lambda: ("finish", True) in _seen)
    assert [_s[:2] for _s in _seen[:2]] == [(1, 2), (2, 2)], f"signals: progress in order {_seen}"
    assert all(_s[2] == threading.get_ident() for _s in _seen[:2]), "signals: received in the GUI thread"


def test_job_popup_flow():
    # 단계 : 돌리기 - 잠금, 멈춤 켜짐, 닫기 꺼짐
    _pop = Job_popup()
    _target = QPushButton("lock me")
    _gate = threading.Event()
    _job = _Fake(3, _gate)
    _pop.run(_job, lock=(_target,))
    assert not _target.isEnabled() and _pop._stop.isEnabled() and not _pop._close.isEnabled(), "run: locked while running"

    # 실패 갈래 : 도는 중에 다시 돌리기
    with pytest.raises(RuntimeError):
        _pop.run(_Fake(1))

    # 단계 : 끝 - 로그, 막대, 잠금 풀림, 닫기 켜짐, 요약
    _gate.set()
    _wait(_pop._close.isEnabled)
    assert _pop.log.toPlainText().splitlines() == ["ok 0", "ok 1", "ok 2"], "finish: log lines"
    assert (_pop.bar.value(), _pop.bar.maximum()) == (3, 3), "finish: bar"
    assert _target.isEnabled() and not _pop._stop.isEnabled(), "finish: unlocked"
    assert _pop.state.text().startswith("끝 - 성공"), f"finish: summary {_pop.state.text()}"

    # 단계 : 멈춤 - 작업의 stop, 실패로 끝
    _gate2 = threading.Event()
    _job2 = _Fake(3, _gate2)
    _pop.run(_job2)
    _pop._stop.click()
    _gate2.set()
    _wait(_pop._close.isEnabled)
    assert _job2.stopped and _pop.state.text().startswith("끝 - 실패"), "stop: job stopped, failed"
    _pop.close()


def test_job_popup_link_flow():
    # 단계 : config 의 link - popup 클래스 그대로, args 는 생성자 인자
    _w = QWidget()
    Fill(_w, {"class": "qt_QVBoxLayout",
              "link": {"job": {"title": "Run", "class": "Job_popup", "args": {"size": [400, 300]}}}})
    _job = _w.link.job
    assert isinstance(_job, Job_popup) and _job.windowTitle() == "Run", "link: Job_popup with title"
    assert (_job.width(), _job.height()) == (400, 300), "link: args to the constructor"
