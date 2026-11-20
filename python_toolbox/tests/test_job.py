"""Job - Work 를 돌리고, 실패를 그 작업 logger 의 ERROR 기록으로 셈. 예외, 실패 기록, 멈춤 요청이 모두 실패로.

입력 파일 없음. 기록은 pytest 의 `caplog` 로 받음.
"""
from __future__ import annotations

import logging
from pathlib import Path

from python_toolbox.run.job import Job


class _Quiet(Job):
    def Work(self) -> None:
        self.log.info("working")


class _Reports_error(Job):
    def Work(self) -> None:
        self.log.getChild("loader").error("broken sample")


class _Raises(Job):
    def Work(self) -> None:
        raise RuntimeError("boom")


class _Stops(Job):
    def Work(self) -> None:
        self.stop()


def test_job_flow(caplog):
    caplog.set_level(logging.INFO)

    # step : clean work succeeds and leaves a summary record
    assert _Quiet(None, Path(".")).Run() is True, "ok: no error record"
    _summary = caplog.records[-1]
    assert _summary.name == "job._Quiet" and _summary.ok is True and _summary.errors == 0, "ok: summary fields"

    # step : an error record from the job logger or its child fails the run
    assert _Reports_error(None, Path(".")).Run() is False, "error record: child logger counted"
    assert caplog.records[-1].errors == 1, "error record: counted once"

    # step : an exception is logged, not raised, and fails the run
    assert _Raises(None, Path(".")).Run() is False, "exception: run failed"
    assert any(_r.exc_info and _r.levelno == logging.ERROR for _r in caplog.records), "exception: logged with trace"

    # step : a stop request fails the run
    assert _Stops(None, Path(".")).Run() is False, "stop: run failed"
    assert caplog.records[-1].stopped is True, "stop: summary says stopped"
