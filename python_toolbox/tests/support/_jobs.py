"""launcher test 의 job 과 설정 - job 프로세스(spawn)가 다시 import 하는 자리라 test 파일 밖.

job 설정 `test_train_job` 하나를 `CONFIGS` 에 등록 - job 다섯이 같이 씀.
- `train` : `model.patch` 를 자기 폴더 `done.txt` 에 씀
- `fail` : ERROR 기록 하나 - 실패 코드
- `crash` : 결과 없이 프로세스가 끝남 - 종료 코드 5
- `killed` : 자기 프로세스에 SIGKILL - 신호로 끊김
- `wait` : 멈춤 요청이 올 때까지 기다림, `LIMIT` 초 지나면 정상 종료 - 멈추면 멈춤 코드
"""
from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field

from python_toolbox.config import CONFIGS, Base_Config
from python_toolbox.registry import Registry
from python_toolbox.run.job import Job, Job_Config

JOBS = Registry[type[Job]]("job", Job)


@dataclass
class Model_Config(Base_Config):
    patch: int = 0
    depth: int = 0


@CONFIGS.Register_module("test_train_job")
@dataclass
class Train_Config(Job_Config):
    max_iters: int = 0
    model: Model_Config = field(default_factory=Model_Config)


@JOBS.Register_module("train")
class Train_Job(Job):
    def Work(self) -> None:
        _dir = self.base_dir / self.name
        _dir.mkdir(exist_ok=True)
        (_dir / "done.txt").write_text(str(self.config.model.patch))


@JOBS.Register_module("fail")
class Fail_Job(Job):
    def Work(self) -> None:
        self.log.error("broken")


@JOBS.Register_module("crash")
class Crash_Job(Job):
    def Work(self) -> None:
        os._exit(5)


@JOBS.Register_module("killed")
class Killed_Job(Job):
    def Work(self) -> None:
        os.kill(os.getpid(), signal.SIGKILL)


@JOBS.Register_module("wait")
class Wait_Job(Job):
    #: 멈춤 요청이 안 오면 스스로 끝낼 때까지(초) - 정상 종료로 끝나 test 가 실패로 봄.
    LIMIT = 10.0

    def Work(self) -> None:
        _until = time.monotonic() + self.LIMIT
        while not self.stopped and time.monotonic() < _until:
            time.sleep(0.05)
