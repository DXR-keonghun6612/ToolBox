"""launcher test 의 job 과 설정 - job 프로세스(spawn)가 다시 import 하는 자리라 test 파일 밖.

job 설정 `test_train_job` 하나를 `CONFIGS` 에 등록 - job 셋이 같이 씀.
- `train` : `model.patch` 를 자기 폴더 `done.txt` 에 씀
- `fail` : ERROR 기록 하나 - 양수 코드
- `crash` : 결과 없이 프로세스가 끝남 - 종료 코드 3
"""
from __future__ import annotations

import os
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
        os._exit(3)
