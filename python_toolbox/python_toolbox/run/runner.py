"""실행의 바탕 - 설정 공간 하나에서 runner 설정을 짓고, 그 설정으로 job 하나를 지어 멤버로 둠. 실행마다 결과 자리 하나(`result/<이름>/<시각_id>`).

runner 설정은 공간의 root 전체. 하위 설정(model, loss 등)은 runner 설정의 설정 필드로 선언 - `Config_Space.Build` 가 함께 지음.
`JOB_REGISTRY` 에 등록한 job 은 `(config, result_dir)` 로 지어짐 - job 은 runner 를 모름.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, get_type_hints

from ..file import Read_from, Write_to
from ..registry import Registry
from ..schema import Base_Config
from .job import Job
from .log import Default_log, Log_Config, Setup_log
from .parser import Config_Space

#: 결과 자리의 맨 위 - 실행한 폴더(cwd) 기준.
RESULT_ROOT = "./result"
#: `Run` 이 결과 자리에 남기는 설정 파일 이름. 프로세스 job 은 `result_dir / CONFIG_FILE` 하나로 같은 설정을 다시 지음.
CONFIG_FILE = "config.yaml"


@dataclass
class Runner_Config(Base_Config):
    """runner 설정의 부모. 사용처가 상속해 자기 필드와 하위 설정 필드를 더함.

    Attributes:
        project_name: 결과 자리 경로에 쓰는 이름. 비면 안 됨.
        job: 돌릴 job 의 `JOB_REGISTRY` key. 비면 안 됨 - argv 로 `job=<key>` 덮어씀.
        resume: 이어서 할 run 폴더. 비면 새 결과 자리.
        log: logger 이름 -> 수준과 출력 위치 - `Setup_log`. argv 로 `log.<이름>.level=DEBUG`.
        shared: 공용 값 자리. 하위 설정이 `${shared.<이름>}` 으로 참조.
    """

    project_name: str = ""
    job: str = ""
    resume: str = ""
    log: dict[str, Log_Config] = field(default_factory=Default_log)
    shared: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_name:
            raise ValueError("project_name is empty")
        if not self.job:
            raise ValueError("job is empty")


class Runner:
    """실행의 바탕. 사용처가 상속해 `config` 타입을 좁힘 - `config: Train_runner_config`.

    Attributes:
        space: 읽은 설정 값의 공간.
        config: 공간 root 에서 지은 runner 설정.
        result_dir: 이번 실행의 결과 자리 - `Make_result_dir` 이 만듦.
        job: `config.job` 으로 고른 job. 생성 때 지음, `Run` 이 시작.
    """

    config: Runner_Config
    #: 하위 설정을 `config_type` 으로 고를 registry. 없으면 선언된 필드 타입.
    CONFIG_REGISTRY: ClassVar[Registry | None] = None
    #: `config.job` 으로 job 클래스를 고를 registry. 없으면 오류.
    JOB_REGISTRY: ClassVar[Registry | None] = None
    #: 이어서 할 때 저장된 설정과 달라도 되는 경로. `job`, `resume`, `log` 은 늘 포함 - 사용처가 더함.
    RESUME_FREE: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, files: Mapping[str, str | Path], argv: Sequence[str] = ()) -> None:
        """Args:
            files: 놓을 경로 -> 설정 파일. root 는 `""`.
            argv: `경로=값` 덮어쓰기.

        Raises:
            ValueError: `files` 가 빔, `project_name`, `job` 이 빔.
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

        if self.config.resume:
            self.result_dir = Path(self.config.resume)
            self.Check_resume()
        else:
            _run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            self.result_dir = Path(RESULT_ROOT) / self.config.project_name / _run_id

        if self.JOB_REGISTRY is None:
            raise TypeError(f"{type(self).__name__}.JOB_REGISTRY is not set")
        _job_cls = self.JOB_REGISTRY.Get(self.config.job, Job)
        self.job = _job_cls(self.config, self.result_dir)

    @property
    def config_path(self) -> Path:
        """`Run` 이 설정을 남기는 파일."""
        return self.result_dir / CONFIG_FILE

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

    def Check_resume(self) -> None:
        """이어서 할 run 폴더의 저장된 설정과 지금 설정을 비교. `job`, `resume`, `log`, `RESUME_FREE` 밖의 경로가 다르면 멈춤.

        Raises:
            FileNotFoundError: run 폴더나 그 안의 설정 파일 없음.
            ValueError: 허용 밖의 경로가 다름 - 다른 경로를 모두 담음.
        """
        _saved_path = self.config_path
        if not _saved_path.is_file():
            raise FileNotFoundError(f"{_saved_path}: no saved config to resume")

        _ok, _saved = Read_from(_saved_path)
        if not _ok or not isinstance(_saved, dict):
            raise ValueError(f"{_saved_path}: cannot read a mapping")

        _free = {"job", "resume", "log"} | self.RESUME_FREE
        _diff = [
            _p for _p in _Diff(_saved, self.config.Serialize(), "")
            if not any(_p == _f or _p.startswith(_f + ".") for _f in _free)
        ]
        if _diff:
            raise ValueError(f"{self.result_dir}: config differs from the saved one at {', '.join(_diff)}")

    def Make_result_dir(self) -> bool:
        """결과 자리를 만듦.

        Returns:
            이번에 새로 만들었으면 참, 이미 있었으면 거짓.
        """
        if self.result_dir.is_dir():
            return False
        self.result_dir.mkdir(parents=True)
        return True

    def Run(self) -> bool:
        """결과 자리를 만들고, 지은 설정을 `config_path` 에 남기고, 기록 handler 를 걸고, job 을 돌림.

        Returns:
            job 이 실패 기록 없이 끝났으면 참 - 진입점의 종료 코드로.
        """
        self.Make_result_dir()
        Write_to(self.config_path, self.config.Serialize())
        Setup_log(self.result_dir, self.config.log)
        return self.job.Run()


def _Diff(saved: Any, current: Any, path: str) -> list[str]:
    """두 값이 다른 경로 목록. dict 는 key 마다 내려감."""
    if isinstance(saved, dict) and isinstance(current, dict):
        _out: list[str] = []
        for _k in sorted(saved.keys() | current.keys(), key=str):
            _p = f"{path}.{_k}" if path else str(_k)
            if _k not in saved or _k not in current:
                _out.append(_p)
            else:
                _out.extend(_Diff(saved[_k], current[_k], _p))
        return _out
    return [] if saved == current else [path]
