"""작업의 바탕 - `(name, config, base_dir)` 로 지어지고, `Work` 를 돌리고, 실패는 그 작업 logger 의 ERROR 기록으로 셈.

진행, 결과, 실패는 모두 logging 으로 남김 - 따로 event 없음. 어느 프로세스에서 돌릴지는 부르는 쪽 몫.
멈춤은 요청만(`stop`) - `Work` 가 `stopped` 를 보고 끝냄.
job 은 자기 이름과 자기 설정(`Job_Config`)만 받음 - launcher 설정의 모양을 모름. 자기 기록 선언(`config.log`)은 `Run` 이 검.
`Run` 의 결과는 `{이름: (코드, 설정 Hash(), 내용)}` - 코드 0 정상 종료, 양수 실패, 음수 멈춤. 코드와 내용은 `Outcome` 이 정함.
job 결과 폴더는 `Make_run_dir` - 새로면 자기 설정을 남기고, 이어서면 남은 설정과 정체성을 비교(`Check_saved`).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..file import Read_from, Write_to
from ..schema import Walk, Walk_rule
from .log import LOG_DIR, Attach, Begin_run, Detach
from .unit import Diff, Unit_Config

#: job 결과 폴더에 남기는 job 설정 파일 이름. 폴더가 job 마다라 이름에 job 을 안 붙임.
CONFIG_FILE = "config.yaml"
#: 정상 종료 코드.
OK = 0
#: 실패 코드 -> 이름. 양수. 1 은 구분 없는 실패 - 사용처가 2 부터 더함.
FAILED: dict[int, str] = {1: "Failed"}
#: 멈춤 코드 -> 이름. 음수 - 프로세스가 신호로 끊긴 `exitcode`(-N) 와 같은 쪽. 사용처가 -2 부터 더함.
STOPPED: dict[int, str] = {-1: "Stopped"}
#: job 결과 하나 - `(코드, 설정 Hash(), 내용)`.
Result = tuple[int, str, str]


@dataclass
class Job_Config(Unit_Config):
    """job 설정의 부모. 사용처가 상속해 job 만의 필드와 job 이 짓는 객체의 설정을 더함.

    `object_type` 이 `JOB_REGISTRY` 의 job 클래스 key. 하위 타입은 `config_type` 으로 고름.

    Attributes:
        resume: 이어 쓸 job 결과 폴더. 비면 새로 - 결과 폴더는 job 이 정함. 정체성 밖.
    """

    resume: str = ""

    __exclude_identity__: ClassVar[set[str]] = {"resume"}


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
        name: job 이름 - 부르는 쪽이 job 을 가르는 key. 결과의 key.
        config: 자기 설정. job 이 짓는 객체의 설정도 그 안에.
        base_dir: job 이 돌 바탕 자리. 자기 결과 폴더, 자기 파일 기록 자리는 job 이 그 아래에 정함.
        log: 이 작업의 logger(`job.<이름>`). 실패는 `log.error` 또는 예외.
        started: 이번 `Run` 의 시작 시각 - `Begin_run`. `Run` 전에는 빔.
    """

    def __init__(self, name: str, config: Job_Config, base_dir: Path) -> None:
        """Args:
            name: job 이름.
            config: 자기 설정.
            base_dir: job 이 돌 바탕 자리.
        """
        self.name = name
        self.config = config
        self.base_dir = base_dir
        self.log = logging.getLogger(f"job.{name}")
        self.started = ""
        self._stop = threading.Event()

    def Make_run_dir(self) -> Path:
        """job 결과 폴더를 정함. 사용처가 override 해 이름을 바꿈 - 이어서 할 때의 확인은 `Check_saved`.

        `config.resume` 이 비면 바탕 자리 아래 새 `<시각_id>` 를 만들고 자기 설정을 `CONFIG_FILE` 로 남김.
        있으면 그 폴더에 남은 설정과 정체성을 비교.

        Raises:
            FileNotFoundError: 이어 쓸 폴더나 그 안의 설정 파일 없음.
            ValueError: 남은 설정과 다름 - 다른 경로를 모두 담음.
        """
        if not self.config.resume:
            _dir = self.base_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            _dir.mkdir()
            Write_to(_dir / CONFIG_FILE, Walk(self.config, Walk_rule()))   # key 는 필드 이름 - 공간, Diff 와 같게
            return _dir

        _dir = Path(self.config.resume)
        self.Check_saved(_dir)
        return _dir

    def Check_saved(self, run_dir: Path) -> None:
        """job 결과 폴더에 남은 설정과 자기 설정의 정체성이 같은지 - `unit.Diff`.

        Raises:
            FileNotFoundError: 그 폴더의 설정 파일 없음.
            ValueError: 못 읽음, 정체성이 다름 - 다른 경로를 모두 담음.
        """
        _saved_path = run_dir / CONFIG_FILE
        if not _saved_path.is_file():
            raise FileNotFoundError(f"{_saved_path}: no saved job config")
        _ok, _saved = Read_from(_saved_path)
        if not _ok or not isinstance(_saved, dict):
            raise ValueError(f"{_saved_path}: cannot read a mapping")

        _diff = Diff(_saved, self.config)
        if _diff:
            raise ValueError(f"{run_dir}: job config differs from the saved one at {', '.join(_diff)}")

    def Work(self) -> None:
        """일. 사용처가 구현. 긴 일은 `stopped` 를 보고 일찍 끝냄."""
        raise NotImplementedError(f"{type(self).__name__}.Work")

    def Outcome(self, errors: int) -> tuple[int, str]:
        """이번 실행의 `(코드, 내용)`. 사용처가 override 해 코드와 내용을 자기 것으로 선언.

        코드 0 정상 종료, 양수 실패(`FAILED`), 음수 멈춤(`STOPPED`).
        기본 : 멈춤 요청이 있으면 -1 - 멈춤 중 오류도 멈춤으로, ERROR 기록이 있으면 1, 둘 다 없으면 `(OK, "Done")`.

        Args:
            errors: 이번 실행의 ERROR 기록 수.
        """
        if self.stopped:
            return -1, STOPPED[-1]
        if errors:
            return 1, f"{FAILED[1]} - {errors} error records"
        return OK, "Done"

    def Run(self) -> dict[str, Result]:
        """시작 시각을 정하고 자기 기록 선언을 걸고 `Work` 를 돌림. 예외는 `log.exception` 으로 남기고 실패로 - 다시 던지지 않음.

        아래 logger 의 ERROR 도 셈 - 아래에 자기 선언이 있어도. 선언은 끝나면 뗌.

        Returns:
            `{이름: (코드, 설정 Hash(), 내용)}` - `Outcome`.

        Raises:
            ValueError: 자기 기록 선언이 틀림 - `Attach` 그대로. `Work` 전에.
        """
        self.started = Begin_run()
        if self.config.log is not None:
            Attach(self.log.name, self.config.log, self.base_dir / LOG_DIR)
        _counter = _Error_counter()
        self.log.addHandler(_counter)
        self._stop.clear()
        self.log.info("work started", extra={"job": self.name, "started": self.started})
        _start = time.monotonic()
        try:
            self.Work()
        except Exception:
            self.log.exception("work raised")
        finally:
            self.log.removeHandler(_counter)

        _code, _content = self.Outcome(_counter.count)
        self.log.info(
            "work done" if _code == OK else "work failed",
            extra={"job": self.name, "code": _code, "errors": _counter.count, "stopped": self.stopped,
                   "seconds": round(time.monotonic() - _start, 3)},
        )
        if self.config.log is not None:
            Detach(self.log.name)
        return {self.name: (_code, self.config.Hash(), _content)}

    def stop(self) -> None:
        """멈춤 요청. `Work` 가 `stopped` 를 보고 끝냄 - 강제로 끊지 않음."""
        self._stop.set()

    @property
    def stopped(self) -> bool:
        """이번 실행에 멈춤 요청이 왔나."""
        return self._stop.is_set()
