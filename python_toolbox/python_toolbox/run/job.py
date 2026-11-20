"""작업의 바탕 - `(config, result_dir)` 로 지어지고, `Work` 를 돌리고, 실패는 그 작업 logger 의 ERROR 기록으로 셈.

진행, 결과, 실패는 모두 logging 으로 남김 - 따로 event 없음. 스레드에서 돌릴지는 부르는 쪽 몫.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any


class _Error_counter(logging.Handler):
    """ERROR 이상 record 를 셈. handler 라서 하위 logger 에서 올라온 record 도 봄 - logger filter 는 못 봄."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


class Job:
    """작업 하나. 사용처가 상속해 `Work` 를 구현 - 객체는 그 안에서 지음.

    Attributes:
        config: runner 가 지은 설정 - 하위 설정도 그 안에.
        result_dir: 이번 실행의 결과 자리.
        log: 이 작업의 logger(`job.<클래스 이름>`). 실패는 `log.error` 또는 예외.
    """

    def __init__(self, config: Any, result_dir: Path) -> None:
        self.config = config
        self.result_dir = result_dir
        self.log = logging.getLogger(f"job.{type(self).__name__}")
        self._stop = threading.Event()

    def Work(self) -> None:
        """일. 사용처가 구현. 긴 일은 `stopped` 를 보고 일찍 끝냄."""
        raise NotImplementedError(f"{type(self).__name__}.Work")

    def Run(self) -> bool:
        """`Work` 를 돌림. 예외는 `log.exception` 으로 남기고 실패로 - 다시 던지지 않음, 기록이 실패의 근거.

        Returns:
            ERROR 기록이 없었고 멈춤 요청도 없었으면 참.
        """
        _counter = _Error_counter()
        self.log.addHandler(_counter)
        self._stop.clear()
        _start = time.monotonic()
        try:
            self.Work()
        except Exception:
            self.log.exception("work raised")
        finally:
            self.log.removeHandler(_counter)

        _ok = _counter.count == 0 and not self.stopped
        self.log.info(
            "work done" if _ok else "work failed",
            extra={"ok": _ok, "errors": _counter.count, "stopped": self.stopped,
                   "seconds": round(time.monotonic() - _start, 3)},
        )
        return _ok

    def stop(self) -> None:
        """멈춤 요청. `Work` 가 `stopped` 를 보고 끝냄 - 강제로 끊지 않음."""
        self._stop.set()

    @property
    def stopped(self) -> bool:
        """이번 실행에 멈춤 요청이 왔나."""
        return self._stop.is_set()
