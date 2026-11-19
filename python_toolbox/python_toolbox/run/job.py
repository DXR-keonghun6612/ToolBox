"""작업 - 스레드 일과 프로세스 일을 콜백 계약 하나로. Qt 없음, 화면 없음.

`on(event, fn)` 으로 거는 event. 콜백은 작업이 도는 스레드에서 불림 - GUI 스레드로 넘기는 것은 부르는 쪽

- `start` `()`
- `progress` `(done, total, text)` - `total <= 0` 은 전체를 모름
- `line` `(text)`
- `finish` `(ok, payload)` - 예외, 0 아닌 종료 코드, 멈춤이면 `ok` 거짓

출력 줄 규약 - `ok <key>` / `fail <key> <reason>`. 작업 프로그램(쓰는 쪽)과 `Process_job`(읽는 쪽)이 같은 함수
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from collections.abc import Callable
from typing import Any

__all__ = [
    "EVENTS",
    "Call_job",
    "Context",
    "Fail",
    "Flags",
    "Job",
    "Module_job",
    "Ok",
    "Parse",
    "Process_job",
]

#: 작업이 내는 event.
EVENTS = ("start", "progress", "line", "finish")

#: 출력 줄 규약의 첫 낱말.
OK, FAIL = "ok", "fail"


# ── 출력 줄 규약 ──────────────────────────────────────────────────────────────
def Ok(key: Any) -> str:
    """성공한 key 의 줄 - `ok <key>`."""
    return f"{OK} {key}"


def Fail(key: Any, reason: str) -> str:
    """실패한 key 의 줄 - `fail <key> <reason>`."""
    return f"{FAIL} {key} {reason}"


def Parse(line: str) -> tuple[str, str, str] | None:
    """규약 줄 읽기.

    Returns:
        `(kind, key, reason)` - `kind` 는 `"ok"` / `"fail"`. 규약 밖의 줄이면 None.
    """
    _parts = line.strip().split(maxsplit=2)
    if len(_parts) < 2 or _parts[0] not in (OK, FAIL):
        return None
    return _parts[0], _parts[1], _parts[2] if len(_parts) == 3 else ""


def Flags(**kwargs: Any) -> list[str]:
    """키워드 인자 -> 명령 줄 `--이름 값`.

    목록, 튜플은 값마다 한 번. `True` 는 `--이름` 만, `False`, None 은 안 붙임.
    """
    _out: list[str] = []
    for _name, _value in kwargs.items():
        _flag = f"--{_name}"
        if _value is None or _value is False:
            continue
        if _value is True:
            _out.append(_flag)
        elif isinstance(_value, (list, tuple)):
            for _v in _value:
                _out += [_flag, str(_v)]
        else:
            _out += [_flag, str(_value)]
    return _out


# ── 계약 ──────────────────────────────────────────────────────────────────────
class Job:
    """작업 하나. 실행은 서브클래스의 `_run`. 한 번에 하나만 돎."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[..., Any]]] = {_e: [] for _e in EVENTS}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        """시작했고 아직 `finish` 를 안 냈나."""
        return self._running

    @property
    def stopped(self) -> bool:
        """이번 실행에 멈춤을 요청했나."""
        return self._stop.is_set()

    def on(self, event: str, fn: Callable[..., Any]) -> None:
        """콜백을 걺. event 하나에 여럿 가능.

        Raises:
            KeyError: `EVENTS` 밖의 event 일 때.
        """
        if event not in self._subs:
            raise KeyError(f"unknown event {event!r} - known {list(EVENTS)}")
        self._subs[event].append(fn)

    def start(self) -> None:
        """따로 도는 스레드에서 시작.

        Raises:
            RuntimeError: 아직 도는 중일 때 - 조용히 갈아타지 않음.
        """
        if self._running:
            raise RuntimeError("the job is still running")
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._main, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """멈춤 요청. 실행은 그래도 `finish` 로 끝남."""
        self._stop.set()
        self._halt()

    def wait(self, timeout: float | None = None) -> bool:
        """스레드가 끝나길 기다림. 끝났나를 돌려줌."""
        if self._thread is not None:
            self._thread.join(timeout)
        return not self._running

    def _emit(self, event: str, *args: Any) -> None:
        for _fn in list(self._subs[event]):
            _fn(*args)

    def _main(self) -> None:
        self._emit("start")
        try:
            _ok, _payload = self._run()
        except Exception:
            _ok, _payload = False, traceback.format_exc()
        self._running = False
        self._emit("finish", _ok and not self.stopped, _payload)

    def _run(self) -> tuple[bool, Any]:
        """작업의 스레드에서 일을 함. `(ok, payload)` 를 돌려줌."""
        raise NotImplementedError(f"{type(self).__name__}._run")

    def _halt(self) -> None:
        """멈춤 요청 뒤 일을 끊음. 스레드 일은 대신 `Context.stopped` 를 봄."""


# ── 스레드 일 ─────────────────────────────────────────────────────────────────
class Context:
    """스레드 일의 함수가 첫 인자로 받는 것."""

    def __init__(self, job: Job) -> None:
        self._job = job

    def report(self, done: int, total: int, text: str = "") -> None:
        """`progress` 를 냄. `total <= 0` 은 전체를 모름."""
        self._job._emit("progress", done, total, text)

    def line(self, text: str) -> None:
        """`line` 을 냄."""
        self._job._emit("line", text)

    @property
    def stopped(self) -> bool:
        """멈춤 요청이 왔나 - 함수가 보고 일찍 돌아감."""
        return self._job.stopped


class Call_job(Job):
    """스레드에서 `fn(context, *args, **kwargs)`.

    돌려준 값은 `finish(True, 값)`, 예외는 `finish(False, traceback 글자)` - 안 삼킴.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def _run(self) -> tuple[bool, Any]:
        return True, self._fn(Context(self), *self._args, **self._kwargs)


# ── 프로세스 일 ───────────────────────────────────────────────────────────────
class Process_job(Job):
    """명령을 돌리고 출력 줄을 읽음.

    stdout, stderr 합침, 버퍼 없음(`PYTHONUNBUFFERED=1`). 줄마다 `line`, 규약 줄이면 `progress(ok + fail, total, 그 줄)`.
    `finish` 의 payload 는 종료 코드, 0 이면 `ok`.

    `total`, `cwd`, `env` 는 이 클래스가 쓰는 이름 - 그 이름의 flag 는 `argv` 에 직접.

    Attributes:
        argv: 돌릴 명령 - flag 를 붙인 것.
        ok: 이번 실행의 `ok` 줄 수.
        failed: 이번 실행의 `fail` 줄 수.
    """

    def __init__(self, *argv: Any, total: int = 0, cwd: str | os.PathLike | None = None,
                 env: dict[str, str] | None = None, **kwargs: Any) -> None:
        """Args:
            *argv: 명령과 위치 인자.
            total: 기대하는 규약 줄 수. 0 이하면 모름.
            cwd: 작업 폴더.
            env: 지금 환경 위에 더할 변수.
            **kwargs: `argv` 뒤에 붙일 flag - `Flags`.

        Raises:
            ValueError: `argv` 가 비었을 때.
        """
        if not argv:
            raise ValueError("argv is empty - give the command")
        super().__init__()
        self.argv = [str(_a) for _a in argv] + Flags(**kwargs)
        self._total = total
        self._cwd = cwd
        self._env = env
        self._proc: subprocess.Popen | None = None
        self.ok = 0
        self.failed = 0

    def _run(self) -> tuple[bool, Any]:
        self.ok = self.failed = 0
        _env = {**os.environ, **(self._env or {}), "PYTHONUNBUFFERED": "1"}
        self._proc = subprocess.Popen(self.argv, cwd=self._cwd, env=_env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for _raw in self._proc.stdout:
            _line = _raw.rstrip("\n")
            self._emit("line", _line)
            _parsed = Parse(_line)
            if _parsed is None:
                continue
            if _parsed[0] == OK:
                self.ok += 1
            else:
                self.failed += 1
            self._emit("progress", self.ok + self.failed, self._total, _line)
        _code = self._proc.wait()
        return _code == 0, _code

    def _halt(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


class Module_job(Process_job):
    """지금 인터프리터로 `python -m module` - `Process_job(sys.executable, "-m", module, ...)`."""

    def __init__(self, module: str, *args: Any, total: int = 0, cwd: str | os.PathLike | None = None,
                 env: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(sys.executable, "-m", module, *args, total=total, cwd=cwd, env=env, **kwargs)
