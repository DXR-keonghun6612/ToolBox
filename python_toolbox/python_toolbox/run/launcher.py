"""실행 준비와 띄우기 - 설정 공간 하나에서 launcher 설정을 짓고, `jobs` 의 key 마다 job 을 자기 프로세스로 띄우고, 결과가 들어오는 대로 기록.

launcher 설정은 공간의 root 전체이자 설정 트리의 root 단위(`Unit_Config`). job 설정은 `jobs` 의 값(`Job_Config`).
job 이름은 `jobs` 의 key - 사용자가 지정. job 클래스는 그 설정의 `object_type` 으로 `JOB_REGISTRY` 에서.
job 은 자기 프로세스에서 `(이름, 그 job 설정, base_dir)` 로 지어지고 돎 - job 은 launcher 를 모름.
launcher 기록(`LAUNCHER_LOGGER`)은 둘만 - 띄움(이름, 시각), 결과(이름, 코드, hash, 내용). 세부는 job 기록.
바탕 자리는 job 이 돌 자리 - 그 아래 자리는 job 이 정함. launcher 의 파일 기록은 그 아래 `LOG_DIR`. 설정 파일을 안 남김.
진입 둘 - `From_argv`(CLI), `From_files`(코드). 짓는 길은 `From_files` 하나.
"""
from __future__ import annotations

import logging
import multiprocessing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from multiprocessing.connection import Connection, wait
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

from ..config import Config_Space
from ..registry import Registry
from .job import FAILED, Job, Job_Config, Result
from .log import LOG_DIR, Attach, Begin_run, Default_log, Log_Config
from .unit import Unit_Config

#: 바탕 자리의 맨 위 - 실행한 폴더(cwd) 기준.
BASE_ROOT = "./result"
#: launcher 자기 기록의 logger 이름.
LAUNCHER_LOGGER = "launcher"
#: job 프로세스를 띄우는 방식 - 부모의 상태(handler, 열린 자원)를 안 물려받음.
START_METHOD = "spawn"


@dataclass
class Launcher_Config(Unit_Config):
    """launcher 설정의 부모. 사용처가 상속해 `jobs` 의 값 타입을 좁힘.

    Attributes:
        log: launcher 자기 기록의 선언. 기본 `Default_log`. argv 로 `log.level=DEBUG`.
        project_name: 바탕 자리 경로에 쓰는 이름. 비면 안 됨.
        jobs: job 이름 -> 그 job 설정. 비면 안 됨, 값마다 `object_type` 이 `JOB_REGISTRY` key.
        shared: 공용 값 자리. 하위 설정이 `${shared.<이름>}` 으로 참조.
    """

    log: Log_Config | None = field(default_factory=Default_log)
    project_name: str = ""
    jobs: dict[str, Job_Config] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_name:
            raise ValueError("project_name is empty")
        if not self.jobs:
            raise ValueError("jobs is empty")
        _empty = [_n for _n, _j in self.jobs.items() if not _j.object_type]
        if _empty:
            raise ValueError(f"jobs.{_empty[0]}.object_type is empty")


class Launcher:
    """실행 준비와 띄우기. 사용처가 상속해 `config` 타입을 좁히고 `JOB_REGISTRY` 를 둠.

    Attributes:
        space: 읽은 설정 값의 공간.
        config: 공간 root 에서 지은 launcher 설정.
        base_dir: job 이 돌 바탕 자리 - `Make_base_dir` 이 정하고 만듦.
        job_classes: job 이름 -> job 클래스. 생성 때 고름.
        log: launcher 자기 기록의 logger.
    """

    config: Launcher_Config
    #: 하위 설정을 `config_type` 으로 고를 registry. 없으면 선언된 필드 타입.
    CONFIG_REGISTRY: ClassVar[Registry | None] = None
    #: job 설정의 `object_type` 으로 job 클래스를 부를 registry. 없으면 오류.
    JOB_REGISTRY: ClassVar[Registry | None] = None

    def __init__(self, files: Mapping[str, str | Path], argv: Sequence[str] = ()) -> None:
        """Args:
            files: 놓을 경로 -> 설정 파일. root 는 `""`.
            argv: `경로=값` 덮어쓰기.

        Raises:
            ValueError: `files` 가 빔, `project_name`, `jobs`, `object_type` 이 빔.
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

        self.base_dir = self.Make_base_dir()
        (self.base_dir / LOG_DIR).mkdir(exist_ok=True)

        if self.JOB_REGISTRY is None:
            raise TypeError(f"{type(self).__name__}.JOB_REGISTRY is not set")
        self.job_classes: dict[str, type[Job]] = {
            _name: self.JOB_REGISTRY.Get(_job.object_type, Job) for _name, _job in self.config.jobs.items()
        }
        self.log = logging.getLogger(LAUNCHER_LOGGER)

    @classmethod
    def From_files(cls, files: Mapping[str, str | Path], overrides: Sequence[str] = ()):
        """설정 파일과 덮어쓰기로 launcher 를 지음 - 코드에서 띄울 때.

        Args:
            files: 놓을 경로 -> 설정 파일. root 는 `""`.
            overrides: `경로=값` 덮어쓰기.
        """
        return cls(files, overrides)

    @classmethod
    def From_argv(cls, argv: Sequence[str]):
        """argv 로 launcher 를 지음. `=` 가 있으면 덮어쓰기, 없으면 설정 파일 - `path@at` 의 `at` 은 놓을 경로. 짓는 길은 `From_files`.

        예 : `hub.yaml model.yaml@jobs.train.model shared.patch=64`

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
        return cls.From_files(_files, _overrides)

    def Make_base_dir(self) -> Path:
        """바탕 자리를 정하고 만듦. 이미 있으면 그대로 씀. 사용처가 override 해 자리를 바꿈 - 그 아래 `LOG_DIR` 은 `__init__` 이 만듦.

        `self.config` 는 지어진 뒤 - 설정 값으로 자리를 정해도 됨.

        Returns:
            있는 바탕 자리. 기본 `BASE_ROOT/<project_name>`.
        """
        _dir = Path(BASE_ROOT) / self.config.project_name
        _dir.mkdir(parents=True, exist_ok=True)
        return _dir

    def Run(self) -> dict[str, Result]:
        """자기 기록 선언을 걸고, job 마다 프로세스를 띄우고, 결과가 들어오는 대로 기록. 결과를 다 받으면 끝.

        결과 없이 끝난 job 프로세스는 그 프로세스의 `exitcode` 로 기록 - 신호로 끊겼으면 음수, 아니면 양수(`FAILED`).

        Returns:
            job 이름 -> `(코드, 설정 Hash(), 내용)`.

        Raises:
            ValueError: 자기 기록 선언이 틀림 - `Attach` 그대로. 띄우기 전에.
        """
        Begin_run()
        if self.config.log is not None:
            Attach(LAUNCHER_LOGGER, self.config.log, self.base_dir / LOG_DIR)

        _ctx = multiprocessing.get_context(START_METHOD)
        _pending: dict[Connection, tuple[str, Any]] = {}
        for _name, _cls in self.job_classes.items():
            _recv, _send = _ctx.Pipe(duplex=False)
            _proc = _ctx.Process(target=_Run_job, args=(_name, _cls, self.config.jobs[_name], self.base_dir, _send),
                                 name=f"job-{_name}")
            _proc.start()
            _send.close()
            _pending[_recv] = (_name, _proc)
            self.log.info("job launched", extra={"job": _name, "pid": _proc.pid})

        _results: dict[str, Result] = {}
        while _pending:
            for _ready in wait(list(_pending)):
                _conn = cast(Connection, _ready)
                _name, _proc = _pending.pop(_conn)
                try:
                    _out = _conn.recv()
                except EOFError:
                    _proc.join()
                    _code = _proc.exitcode if _proc.exitcode else next(iter(FAILED))
                    _out = {_name: (_code, self.config.jobs[_name].Hash(), "job process ended without a result")}
                _conn.close()
                _proc.join()
                for _n, (_code, _hash, _content) in _out.items():
                    self.log.log(logging.INFO if _code == 0 else logging.ERROR, "job ended",
                                 extra={"job": _n, "code": _code, "hash": _hash, "content": _content})
                _results.update(_out)
        return _results


def _Run_job(name: str, job_cls: type[Job], config: Job_Config, base_dir: Path, conn: Connection) -> None:
    """job 프로세스 하나 - job 을 짓고 돌려 결과를 보냄. 짓기, 기록 선언이 실패하면 그 사유를 결과로. spawn 대상이라 모듈 함수."""
    try:
        _out = job_cls(name, config, base_dir).Run()
    except Exception as _e:  # noqa: BLE001 - 짓기 실패도 결과로 보냄, 다시 던지면 부모는 사유를 모름
        _out = {name: (next(iter(FAILED)), config.Hash(), f"{type(_e).__name__}: {_e}")}
    conn.send(_out)
    conn.close()
