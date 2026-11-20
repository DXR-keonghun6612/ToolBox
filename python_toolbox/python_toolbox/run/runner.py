"""실행의 바탕 - 설정 공간 하나에서 runner 설정을 짓고, 그 설정으로 job 하나를 지어 멤버로 둠. job 관리만 - 설정 파일을 안 남김.

runner 설정은 공간의 root 전체. 하위 설정(model, loss 등)은 runner 설정의 설정 필드로 선언 - `Config_Space.Build` 가 함께 지음.
job 설정은 runner 설정의 `job` 필드(`Job_Config`) - 설정을 다 지은 뒤 그 `object_type` 으로 `JOB_REGISTRY` 에서 job 클래스를 부름.
job 은 `(config, result_dir)` 로 지어짐 - job 은 runner 를 모름.
결과 자리는 job 결과 폴더들의 부모 - job 결과 폴더는 job 이 그 아래에 만듦. 기록은 그 아래 `LOG_DIR`.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, get_type_hints

from ..registry import Registry
from ..schema import Base_Config
from .job import Job, Job_Config
from .log import Default_log, Log_Config, Setup_log
from .parser import Config_Space

#: 결과 자리의 맨 위 - 실행한 폴더(cwd) 기준.
RESULT_ROOT = "./result"
#: 결과 자리 아래 기록 폴더 이름 - `Setup_log` 의 출력 위치.
LOG_DIR = "log"


@dataclass
class Runner_Config(Base_Config):
    """runner 설정의 부모. 사용처가 상속해 자기 필드와 하위 설정 필드를 더함.

    Attributes:
        project_name: 결과 자리 경로에 쓰는 이름. 비면 안 됨.
        job: 돌릴 job 의 설정. `job.object_type` 이 `JOB_REGISTRY` key - 비면 안 됨, argv 로 `job.object_type=<key>`.
        log: logger 이름 -> 수준과 출력 위치 - `Setup_log`. argv 로 `log.<이름>.level=DEBUG`.
        shared: 공용 값 자리. 하위 설정이 `${shared.<이름>}` 으로 참조.
    """

    project_name: str = ""
    job: Job_Config = field(default_factory=Job_Config)
    log: dict[str, Log_Config] = field(default_factory=Default_log)
    shared: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_name:
            raise ValueError("project_name is empty")
        if not self.job.object_type:
            raise ValueError("job.object_type is empty")


class Runner:
    """실행의 바탕. 사용처가 상속해 `config` 타입을 좁힘 - `config: Train_runner_config`.

    Attributes:
        space: 읽은 설정 값의 공간.
        config: 공간 root 에서 지은 runner 설정.
        result_dir: job 결과 폴더들의 부모 - `Make_result_dir` 이 정하고 만듦.
        job: `config.job.object_type` 으로 부른 job. 생성 때 지음, `Run` 이 시작.
    """

    config: Runner_Config
    #: 하위 설정을 `config_type` 으로 고를 registry. 없으면 선언된 필드 타입.
    CONFIG_REGISTRY: ClassVar[Registry | None] = None
    #: `config.job.object_type` 으로 job 클래스를 부를 registry. 없으면 오류.
    JOB_REGISTRY: ClassVar[Registry | None] = None

    def __init__(self, files: Mapping[str, str | Path], argv: Sequence[str] = ()) -> None:
        """Args:
            files: 놓을 경로 -> 설정 파일. root 는 `""`.
            argv: `경로=값` 덮어쓰기.

        Raises:
            ValueError: `files` 가 빔, `project_name`, `job.object_type` 이 빔.
            TypeError: `JOB_REGISTRY` 가 없음. 설정 공간이 낸 그대로 - 없는 필드.
            KeyError: 등록 안 된 job. 설정 공간이 낸 그대로 - 없는 경로.
        """
        if not files:
            raise ValueError("no config file given")

        _type = get_type_hints(type(self))["config"]
        self.space = Config_Space()
        self.space.Load_schema(_type)
        for _at, _path in files.items():
            self.space.Load(_path, _at)
        self.space.Override(list(argv))
        self.config = self.space.Build(_type, registry=self.CONFIG_REGISTRY)

        self.result_dir = self.Make_result_dir()
        (self.result_dir / LOG_DIR).mkdir(exist_ok=True)

        if self.JOB_REGISTRY is None:
            raise TypeError(f"{type(self).__name__}.JOB_REGISTRY is not set")
        _job_cls = self.JOB_REGISTRY.Get(self.config.job.object_type, Job)
        self.job = _job_cls(self.config, self.result_dir)

    @classmethod
    def From_argv(cls, argv: Sequence[str]):
        """argv 로 runner 를 지음. `=` 가 있으면 덮어쓰기, 없으면 설정 파일 - `path@at` 의 `at` 은 놓을 경로.

        예 : `hub.yaml model.yaml@model shared.patch=64`

        Raises:
            ValueError: 설정 파일이 없음, 같은 경로에 파일 둘.
        """
        _files: dict[str, str] = {}
        _overrides: list[str] = []
        for _item in argv:
            if "=" in _item:
                _overrides.append(_item)
                continue
            _path, _, _at = _item.partition("@")
            if _at in _files:
                raise ValueError(f"{_item}: two config files at '{_at or '<root>'}'")
            _files[_at] = _path

        if not _files:
            raise ValueError("no config file in argv")
        return cls(_files, _overrides)

    def Make_result_dir(self) -> Path:
        """결과 자리를 정하고 만듦. 이미 있으면 그대로 씀. 사용처가 override 해 자리를 바꿈 - 그 아래 `LOG_DIR` 은 `__init__` 이 만듦.

        `self.config` 는 지어진 뒤 - 설정 값으로 자리를 정해도 됨.

        Returns:
            있는 결과 자리. 기본 `RESULT_ROOT/<project_name>`.
        """
        _dir = Path(RESULT_ROOT) / self.config.project_name
        _dir.mkdir(parents=True, exist_ok=True)
        return _dir

    def Run(self) -> bool:
        """기록 handler 를 결과 자리의 `LOG_DIR` 에 걸고 job 을 돌림.

        Returns:
            job 이 실패 기록 없이 끝났으면 참 - 진입점의 종료 코드로.
        """
        Setup_log(self.result_dir / LOG_DIR, self.config.log)
        return self.job.Run()
