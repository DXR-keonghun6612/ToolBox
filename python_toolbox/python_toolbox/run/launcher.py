"""실행 준비와 띄우기 - launcher 설정 파일 하나로 자기 설정과 meta 를 만들고, `Run` 때 meta 의 job 마다 설정을 지어 자기 프로세스로 띄우고, 결과가 들어오는 대로 기록.

launcher 설정은 진입점마다 하나, meta 와 따로 - 클래스는 `config` annotation, `config_type` 없음. 사용처는 상속해 선언만.
meta 는 launcher 설정의 `meta` 칸 - 맨 위 key 가 job 이름, 값이 job 설정. 안의 `file@` 는 launcher 설정 파일의 폴더 기준.
job 설정의 클래스는 `config_type`(`CONFIGS`), job 클래스는 `object_type`(`JOB_REGISTRY`).
`Run` 은 모든 job 설정과 job 클래스를 먼저 고른 뒤 띄움 - 하나라도 실패하면 아무것도 안 띄움. meta 가 바뀌면 다음 `Run` 에 반영.
job 은 자기 프로세스에서 `(이름, 그 job 설정, base_dir)` 로 지어지고 돎 - job 은 launcher 를 모름.
launcher 기록(`LAUNCHER_LOGGER`)은 둘만 - 띄움(이름, 시각), 결과(이름, 코드, hash, 내용). 세부는 job 기록.
바탕 자리는 job 이 돌 자리 - 그 아래 자리는 job 이 정함. launcher 의 파일 기록은 그 아래 `LOG_DIR`. 설정 파일을 안 남김.
"""
from __future__ import annotations

import logging
import multiprocessing
from collections.abc import Sequence
from dataclasses import dataclass, field
from multiprocessing.connection import Connection, wait
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

from ..config import Config_Space
from ..file import Read_from
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
    """launcher 설정의 부모. 사용처가 상속해 자기 칸을 더함.

    Attributes:
        log: launcher 자기 기록의 선언. 기본 `Default_log`.
        project_name: 바탕 자리 경로에 쓰는 이름.
        meta: job 이름 -> 그 job 설정. `file@`, `config@`, `${경로}` 를 씀 - `Config_Space` 가 펼치고 풂.
    """

    log: Log_Config | None = field(default_factory=Default_log)
    project_name: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class Launcher:
    """실행 준비와 띄우기. 사용처가 상속해 `config` 타입을 좁히고 `JOB_REGISTRY` 를 둠.

    Attributes:
        config: launcher 설정 파일에서 지은 자기 설정.
        space: job 설정의 meta - 값 변경은 여기에(`space.Override`).
        base_dir: job 이 돌 바탕 자리 - `Make_base_dir` 이 정하고 만듦.
        log: launcher 자기 기록의 logger.
    """

    config: Launcher_Config
    #: job 설정의 `object_type` 으로 job 클래스를 부를 registry. 없으면 오류. 설정 클래스는 `CONFIGS`.
    JOB_REGISTRY: ClassVar[Registry | None] = None

    def __init__(self, config_file: str | Path, overrides: Sequence[str] = ()) -> None:
        """launcher 설정 파일로 자기 설정을 짓고, 그 `meta` 와 덮어쓰기로 공간을 만들고, 바탕 자리를 정함.

        Args:
            config_file: launcher 설정 파일.
            overrides: meta 의 `경로=값`. `file@` 는 cwd 기준.

        Raises:
            TypeError: `JOB_REGISTRY` 가 없음. 설정 짓기의 오류 그대로 - 모르는 칸, 칸 값 타입.
            FileNotFoundError: launcher 설정 파일 없음. 공간의 펼침 오류 그대로.
            ValueError: launcher 설정 파일을 못 읽음, 최상위가 dict 아님. 공간의 덮어쓰기 오류 그대로.
        """
        if self.JOB_REGISTRY is None:
            raise TypeError(f"{type(self).__name__}.JOB_REGISTRY is not set")

        _path = Path(config_file).resolve()
        if not _path.is_file():
            raise FileNotFoundError(f"{_path}: launcher config file not found")
        _ok, _data = Read_from(_path)
        if not _ok or not isinstance(_data, dict):
            raise ValueError(f"{_path}: cannot read a mapping")

        self.config = get_type_hints(type(self))["config"].From_dict(_data)
        self.space = Config_Space(self.config.meta, _path.parent)
        self.space.Override(list(overrides))

        self.base_dir = self.Make_base_dir()
        (self.base_dir / LOG_DIR).mkdir(exist_ok=True)
        self.log = logging.getLogger(LAUNCHER_LOGGER)

    @classmethod
    def From_argv(cls, argv: Sequence[str]):
        """argv 로 launcher 를 지음 - 첫 항목은 launcher 설정 파일, 나머지는 모두 meta 의 `경로=값`.

        예 : `launcher.yaml train=file@./other.yaml train.max_iters=10`

        Raises:
            ValueError: argv 가 빔, `=` 없는 덮어쓰기.
        """
        if not argv:
            raise ValueError("no launcher config file in argv")
        return cls(argv[0], argv[1:])

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
        """meta 의 job 마다 설정과 job 클래스를 고르고, 자기 기록 선언을 걸고, job 마다 프로세스를 띄움. 결과가 들어오는 대로 기록.

        결과 없이 끝난 job 프로세스는 그 프로세스의 `exitcode` 로 기록 - 신호로 끊겼으면 음수, 아니면 양수(`FAILED`).

        Returns:
            job 이름 -> `(코드, 설정 Hash(), 내용)`.

        Raises:
            KeyError, ValueError, TypeError: job 설정 짓기, 등록 안 된 `object_type` - 띄우기 전에.
            ValueError: 자기 기록 선언이 틀림 - `Attach` 그대로. 띄우기 전에.
        """
        _registry = cast(Registry, self.JOB_REGISTRY)
        _configs: dict[str, Job_Config] = {_name: self.space.Build(_name, Job_Config) for _name in self.space.Get()}
        _classes: dict[str, type[Job]] = {_n: _registry.Get(_c.object_type, Job) for _n, _c in _configs.items()}

        Begin_run()
        if self.config.log is not None:
            Attach(LAUNCHER_LOGGER, self.config.log, self.base_dir / LOG_DIR)

        _ctx = multiprocessing.get_context(START_METHOD)
        _pending: dict[Connection, tuple[str, Any]] = {}
        for _name, _cls in _classes.items():
            _recv, _send = _ctx.Pipe(duplex=False)
            _proc = _ctx.Process(target=_Run_job, args=(_name, _cls, _configs[_name], self.base_dir, _send),
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
                    _out = {_name: (_code, _configs[_name].Hash(), "job process ended without a result")}
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
