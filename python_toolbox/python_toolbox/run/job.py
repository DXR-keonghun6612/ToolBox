"""작업의 바탕 - `(config, result_dir)` 로 지어지고, `Work` 를 돌리고, 실패는 그 작업 logger 의 ERROR 기록으로 셈.

진행, 결과, 실패는 모두 logging 으로 남김 - 따로 event 없음. 스레드에서 돌릴지는 부르는 쪽 몫.
job 설정(`Job_Config`)은 runner 설정의 `job` 필드 - job 은 `config.job` 에서 자기 설정을 읽음.
job 결과 폴더는 `Make_run_dir` - 새로면 자기 job 설정을 남기고, 이어서면 남은 설정과 자기 job 설정을 비교.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..file import Read_from, Write_to
from ..schema import Base_Config

#: job 결과 폴더에 남기는 job 설정 파일 이름. 폴더가 job 마다라 이름에 job 을 안 붙임.
CONFIG_FILE = "config.yaml"
#: 이어서 할 때 비교 밖 - 설정 값이 아니라 고르기와 자리.
NOT_COMPARED = frozenset({"resume", "config_type", "object_type"})


@dataclass
class Job_Config(Base_Config):
    """job 설정의 부모. 사용처가 상속해 job 만의 필드를 더함.

    `object_type` 이 `JOB_REGISTRY` 의 job 클래스 key. 하위 타입은 `config_type` 으로 고름.

    Attributes:
        resume: 이어 쓸 job 결과 폴더. 비면 새로 - 결과 폴더는 job 이 정함.
    """

    resume: str = ""


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
        config: runner 가 지은 설정 - 자기 설정은 `config.job`, 하위 설정도 그 안에.
        result_dir: job 결과 폴더들의 부모. 자기 결과 폴더는 job 이 그 아래에 만듦.
        log: 이 작업의 logger(`job.<클래스 이름>`). 실패는 `log.error` 또는 예외.
    """

    def __init__(self, config: Any, result_dir: Path) -> None:
        self.config = config
        self.result_dir = result_dir
        self.log = logging.getLogger(f"job.{type(self).__name__}")
        self._stop = threading.Event()

    def Make_run_dir(self) -> Path:
        """job 결과 폴더를 정함. 사용처가 override 해 이름을 바꿈.

        `config.job.resume` 이 비면 결과 자리 아래 새 `<시각_id>` 를 만들고 자기 job 설정을 `CONFIG_FILE` 로 남김.
        있으면 그 폴더에 남은 설정과 자기 job 설정을 비교 - 남은 설정에 있는 값만, `NOT_COMPARED` 밖.

        Raises:
            FileNotFoundError: 이어 쓸 폴더나 그 안의 설정 파일 없음.
            ValueError: 남은 설정과 다름 - 다른 경로를 모두 담음.
        """
        _job = self.config.job
        if not _job.resume:
            _dir = self.result_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            _dir.mkdir()
            Write_to(_dir / CONFIG_FILE, _job.Serialize())
            return _dir

        _dir = Path(_job.resume)
        _saved_path = _dir / CONFIG_FILE
        if not _saved_path.is_file():
            raise FileNotFoundError(f"{_saved_path}: no saved job config to resume")
        _ok, _saved = Read_from(_saved_path)
        if not _ok or not isinstance(_saved, dict):
            raise ValueError(f"{_saved_path}: cannot read a mapping")

        _diff = _Diff({_k: _v for _k, _v in _saved.items() if _k not in NOT_COMPARED}, _job.Serialize(), "")
        if _diff:
            raise ValueError(f"{_dir}: job config differs from the saved one at {', '.join(_diff)}")
        return _dir

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


def _Diff(saved: Any, current: Any, path: str) -> list[str]:
    """남은 값과 지금 값이 다른 경로 목록. dict 는 남은 값의 key 마다 내려감 - 남은 값에 없는 key 는 안 봄."""
    if isinstance(saved, dict) and isinstance(current, dict):
        _out: list[str] = []
        for _k in sorted(saved.keys(), key=str):
            _p = f"{path}.{_k}" if path else str(_k)
            if _k not in current:
                _out.append(_p)
            else:
                _out.extend(_Diff(saved[_k], current[_k], _p))
        return _out
    return [] if saved == current else [path]
