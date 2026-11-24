"""`Launch_progress` test 의 job 과 설정 - job 프로세스(spawn)가 다시 import 하는 자리라 test 파일 밖.

job 설정 `ui_test_job` 하나를 `CONFIGS` 에 등록 - job 셋이 같이 씀.
- `quick` : 바로 끝남 - 정상 종료
- `fail` : ERROR 기록 하나 - 실패
- `wait` : 멈춤 요청이 올 때까지 기다림, `LIMIT` 초 지나면 정상 종료 - 멈추면 멈춤 코드
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from python_toolbox.config import CONFIGS
from python_toolbox.registry import Registry
from python_toolbox.run.job import Job, Job_Config
from python_toolbox.run.launcher import Launcher

JOBS = Registry[type[Job]]("ui_test_job", Job)


@CONFIGS.Register_module("ui_test_job")
@dataclass
class Ui_Test_Job_Config(Job_Config):
    pass


@JOBS.Register_module("quick")
class Quick_Job(Job):
    def Work(self) -> None:
        self.log.info("quick work")


@JOBS.Register_module("fail")
class Fail_Job(Job):
    def Work(self) -> None:
        self.log.error("broken")


@JOBS.Register_module("wait")
class Wait_Job(Job):
    #: 멈춤 요청이 안 오면 스스로 끝낼 때까지(초).
    LIMIT = 10.0

    def Work(self) -> None:
        _until = time.monotonic() + self.LIMIT
        while not self.stopped and time.monotonic() < _until:
            time.sleep(0.05)


class Ui_Launcher(Launcher):
    JOB_REGISTRY = JOBS
