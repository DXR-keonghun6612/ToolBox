"""작업 - 출력 줄 규약, flag, 스레드 일(값, 예외, 멈춤, 겹친 시작), 프로세스 일(줄, 규약, 종료 코드), 모르는 event.

프로세스 일은 지금 인터프리터의 `-c` 로 짧은 프로그램을 돌림 - 입력 파일 없음.
"""
from __future__ import annotations

import sys
import threading

import pytest

from python_toolbox.run.job import Call_job, Fail, Flags, Module_job, Ok, Parse, Process_job


def _record(job) -> list:
    """event 를 차례로 모음."""
    _got: list = []
    job.on("start", lambda: _got.append(("start",)))
    job.on("progress", lambda d, t, s: _got.append(("progress", d, t, s)))
    job.on("line", lambda s: _got.append(("line", s)))
    job.on("finish", lambda ok, p: _got.append(("finish", ok, p)))
    return _got


def test_protocol_flow():
    # 단계 : 쓰기와 읽기가 같은 꼴
    assert Parse(Ok("a1")) == ("ok", "a1", ""), "protocol: ok line"
    assert Parse(Fail("b2", "no file")) == ("fail", "b2", "no file"), "protocol: fail line with reason"
    assert Parse("progress 3") is None and Parse("ok") is None, "protocol: other lines"

    # 단계 : flag - 목록은 값마다, True 는 이름만, False · None 은 없음
    assert Flags(folder="x", key=["a", "b"], dry=True, skip=False, none=None) == \
        ["--folder", "x", "--key", "a", "--key", "b", "--dry"], "flags: forms"


def test_call_job_flow():
    # 단계 : 값 - start, progress, finish(True, 값)
    def _work(ctx, n, scale=1):
        for _i in range(n):
            ctx.report(_i + 1, n, f"step {_i}")
        return n * scale

    _job = Call_job(_work, 2, scale=10)
    _got = _record(_job)
    _job.start()
    assert _job.wait(5), "value: finished in time"
    assert _got == [("start",), ("progress", 1, 2, "step 0"), ("progress", 2, 2, "step 1"), ("finish", True, 20)], \
        f"value: events {_got}"

    # 단계 : 예외 - 안 삼키고 finish(False, traceback)
    def _boom(ctx):
        raise ValueError("bad input")

    _bad = Call_job(_boom)
    _got = _record(_bad)
    _bad.start()
    _bad.wait(5)
    assert _got[-1][:2] == ("finish", False) and "ValueError: bad input" in _got[-1][2], "exception: traceback"

    # 단계 : 멈춤 - 함수가 stopped 를 보고 돌아감, finish 는 거짓
    _gate = threading.Event()

    def _long(ctx):
        _gate.wait(5)
        return "stopped" if ctx.stopped else "done"

    _slow = Call_job(_long)
    _got = _record(_slow)
    _slow.start()

    # 실패 갈래 : 도는 중에 다시 시작
    with pytest.raises(RuntimeError):
        _slow.start()

    _slow.stop()
    _gate.set()
    _slow.wait(5)
    assert _got[-1] == ("finish", False, "stopped") and not _slow.running, "stop: finish false"

    # 실패 갈래 : 모르는 event
    with pytest.raises(KeyError):
        _slow.on("done", print)


def test_process_job_flow(tmp_path):
    # 단계 : 줄과 규약 - 줄마다 line, 규약 줄이면 progress, 종료 코드 0
    _code = "import sys; print('start'); print('ok a'); print('fail b missing'); print('end')"
    _job = Process_job(sys.executable, "-c", _code, total=2, cwd=tmp_path)
    _got = _record(_job)
    _job.start()
    assert _job.wait(10), "process: finished in time"
    assert [_g[1] for _g in _got if _g[0] == "line"] == ["start", "ok a", "fail b missing", "end"], "process: lines"
    assert [_g[1:3] for _g in _got if _g[0] == "progress"] == [(1, 2), (2, 2)], "process: progress from protocol"
    assert _got[-1] == ("finish", True, 0) and (_job.ok, _job.failed) == (1, 1), "process: exit 0, counts"

    # 단계 : 0 아닌 종료 코드 - finish 거짓
    _fail = Process_job(sys.executable, "-c", "import sys; sys.exit(3)")
    _got = _record(_fail)
    _fail.start()
    _fail.wait(10)
    assert _got[-1] == ("finish", False, 3), "process: non-zero exit"

    # 단계 : 모듈 - sys.executable -m 모듈, flag 는 뒤
    _mod = Module_job("json.tool", "--help", indent=2, compact=True)
    assert _mod.argv == [sys.executable, "-m", "json.tool", "--help", "--indent", "2", "--compact"], "module: argv"

    # 실패 갈래 : 빈 명령
    with pytest.raises(ValueError):
        Process_job()
