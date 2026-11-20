"""진행 화면 - begin 으로 잠그고, 다른 스레드에서 온 report, line, end 가 GUI 스레드에서 보이고, 멈춤은 신호만, config 의 link.

입력 파일 없음. 다른 스레드는 `threading.Thread` 하나.
"""

from __future__ import annotations

import threading

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QWidget

from ui_toolbox.page import Fill, Progress_popup


def _wait(ready, ms: int = 2000) -> None:
    """`ready()` 가 참이 될 때까지 이벤트를 돌림 - 다른 스레드의 신호가 GUI 스레드로 오게. 시간 안에 안 서면 실패."""
    for _ in range(ms // 10):
        if ready():
            return
        QTest.qWait(10)
    raise AssertionError("wait: condition not met in time")


def test_progress_popup_flow():
    _pop = Progress_popup()
    _target = QPushButton("lock me")

    # step : begin - locked, stop on, close off
    _pop.begin(lock=(_target,))
    assert not _target.isEnabled() and _pop._stop.isEnabled() and not _pop._close.isEnabled(), "begin: locked"
    with pytest.raises(RuntimeError):
        _pop.begin()

    # step : report, line, end from another thread - shown in the GUI thread
    _seen_thread: list = []
    _pop._lined.connect(lambda _t: _seen_thread.append(threading.get_ident()))

    def _work() -> None:
        for _i in range(3):
            _pop.line(f"key {_i} done")
            _pop.report(_i + 1, 3, f"key {_i}")
        _pop.end(True, "3 keys")

    threading.Thread(target=_work).start()
    _wait(lambda: not _pop.running)
    assert _pop.log.toPlainText().splitlines() == ["key 0 done", "key 1 done", "key 2 done"], "end: log lines"
    assert (_pop.bar.value(), _pop.bar.maximum()) == (3, 3), "end: bar"
    assert _target.isEnabled() and _pop._close.isEnabled() and not _pop._stop.isEnabled(), "end: unlocked"
    assert _pop.state.text() == "끝 - 성공 · 3 / 3 · 3 keys", f"end: summary {_pop.state.text()}"
    assert set(_seen_thread) == {threading.get_ident()}, "end: received in the GUI thread"

    # step : stop button only signals - the connector decides, then ends as failed
    _asked: list = []
    _pop.stop_requested.connect(lambda: _asked.append(True))
    _pop.begin()
    _pop._stop.click()
    assert _asked == [True] and not _pop._stop.isEnabled(), "stop: signal once"
    _pop.end(False, "stopped")
    _wait(lambda: not _pop.running)
    assert _pop.state.text().startswith("끝 - 실패"), "stop: ended as failed"
    _pop.close()

    # step : config link - popup class by name, args to the constructor
    _w = QWidget()
    Fill(_w, {"class": "qt_QVBoxLayout",
              "link": {"run": {"title": "Run", "class": "Progress_popup", "args": {"size": [400, 300]}}}})
    _run = _w.link.run
    assert isinstance(_run, Progress_popup) and _run.windowTitle() == "Run", "link: Progress_popup with title"
    assert (_run.width(), _run.height()) == (400, 300), "link: args to the constructor"
