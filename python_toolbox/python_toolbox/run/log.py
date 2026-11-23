"""실행 기록 - logger 하나에 자기 선언(수준, 출력 목록)을 거는 표준 logging 설정. 기록하는 쪽은 `logging.getLogger(이름)` 만 씀.

출력 하나 = 형식(`FORMATS`) + 방향(`STREAMS` 의 흐름 또는 기록 폴더 안 파일 이름). 파일 이름의 `TIME_SLOT` 은 그 실행의 시작 시각.
선언한 logger 의 record 는 그 선언의 출력에만 - 위 선언의 출력은 가장 가까운 선언이 자기가 아닌 record 를 거름.
`propagate` 는 그대로 - 위쪽 logger 에 건 handler 는 아래 record 를 다 봄.
같은 방향은 실제 출력 하나를 같이 씀 - 선언 여럿이 같은 파일을 적어도 한 번만 열림.
"""
from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from ..config import Base_Config

#: text 형식 한 줄.
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
#: 바탕 자리 아래 기록 폴더 이름 - 파일 출력의 자리.
LOG_DIR = "log"
#: 기본 text 기록 파일.
LOG_FILE = "run.log"
#: 기본 JSON Lines 기록 파일.
EVENT_FILE = "events.jsonl"
#: 파일 이름 안의 이 자리를 그 실행의 시작 시각으로 - `Begin_run`.
TIME_SLOT = "{time}"

#: 표준 수준 이름 -> 값.
LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

#: LogRecord 가 원래 가진 속성 - 이것 밖은 `extra` 로 들어온 필드.
_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class Json_formatter(logging.Formatter):
    """record 하나를 JSON 한 줄로 - `time`, `level`, `name`, `message`, `extra` 필드, 예외면 `exc`."""

    def format(self, record: logging.LogRecord) -> str:
        _out: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        _out.update({_k: _v for _k, _v in record.__dict__.items() if _k not in _RECORD_KEYS})
        if record.exc_info:
            _out["exc"] = self.formatException(record.exc_info)
        return json.dumps(_out, ensure_ascii=False, default=str)


#: 형식 이름 -> formatter 를 짓는 것. 형식을 더할 때 한 줄.
FORMATS: dict[str, Callable[[], logging.Formatter]] = {
    "text": lambda: logging.Formatter(TEXT_FORMAT),
    "json": Json_formatter,
}
#: 흐름 이름 -> 흐름. 걸 때 읽음 - 바꿔 끼운 `sys.stdout` 도 따름. 이것 밖의 방향은 파일 이름.
STREAMS: dict[str, Callable[[], TextIO]] = {
    "stdout": lambda: sys.stdout,
    "stderr": lambda: sys.stderr,
}


@dataclass
class Log_Output(Base_Config):
    """출력 하나.

    Attributes:
        format: `FORMATS` 의 이름.
        to: `STREAMS` 의 이름, 아니면 기록 폴더 안 파일 이름. 파일 이름의 `TIME_SLOT` 은 실행 시작 시각.
    """

    format: str = "text"
    to: str = "stderr"


@dataclass
class Log_Config(Base_Config):
    """logger 하나의 선언 - 수준과 출력 목록.

    Attributes:
        level: `LEVELS` 의 이름.
        output: 출력 목록.
    """

    level: str = "INFO"
    output: list[Log_Output] = field(default_factory=lambda: [Log_Output()])


def Default_log() -> Log_Config:
    """기본 선언 - `INFO` 로 stderr text, `LOG_FILE` text, `EVENT_FILE` JSON."""
    return Log_Config(level="INFO", output=[
        Log_Output(format="text", to="stderr"),
        Log_Output(format="text", to=LOG_FILE),
        Log_Output(format="json", to=EVENT_FILE),
    ])


class _Target:
    """실제 출력 하나 - 흐름 또는 파일. 선언 여럿이 같이 씀."""

    def __init__(self, handler: logging.Handler, format: str) -> None:
        self.handler = handler
        self.format = format
        self.users = 0


class _Route(logging.Handler):
    """선언 하나가 출력 하나에 거는 handler. 가장 가까운 선언이 자기인 record 만 출력으로 넘김."""

    def __init__(self, owner: str, target: _Target) -> None:
        super().__init__()
        self.owner = owner
        self.target = target

    def emit(self, record: logging.LogRecord) -> None:
        if _Nearest(record.name) == self.owner:
            self.target.handler.handle(record)


#: 지금 걸린 선언 - logger 이름(root 는 `""`) -> 그 선언의 handler.
_DECLARED: dict[str, list[_Route]] = {}
#: 지금 열린 실제 출력 - 방향(흐름 이름 또는 파일 절대 경로) -> 출력.
_TARGETS: dict[str, _Target] = {}
#: 이번 실행의 시작 시각 - `TIME_SLOT` 자리.
_RUN_TIME: str | None = None


def Begin_run() -> str:
    """새 실행 - 시작 시각을 정함. 그 뒤에 거는 파일 이름의 `TIME_SLOT` 이 이 값.

    Returns:
        시작 시각 `YYYYmmdd_HHMMSS_fff`.
    """
    global _RUN_TIME
    _RUN_TIME = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return _RUN_TIME


def Run_time() -> str:
    """이번 실행의 시작 시각. 아직 없으면 지금으로 정함."""
    return _RUN_TIME if _RUN_TIME is not None else Begin_run()


def Attach(name: str, log: Log_Config, log_dir: str | Path | None) -> None:
    """logger 하나에 선언을 검. 이미 걸린 선언은 떼고 바꿈 - 다시 걸어도 겹치지 않음.

    Args:
        name: logger 이름. root 는 `""`.
        log: 그 logger 의 선언.
        log_dir: 파일 출력의 폴더. 없으면 만듦. 파일 출력이 없으면 `None` 가능.

    Raises:
        ValueError: 모르는 수준, 모르는 형식, 폴더 없이 파일 출력, 같은 방향에 다른 형식.
    """
    _level = LEVELS.get(log.level.upper())
    if _level is None:
        raise ValueError(f"log {name or '<root>'}: unknown log level {log.level}")

    _plan: list[tuple[str, Log_Output]] = []
    for _out in log.output:
        if _out.format not in FORMATS:
            raise ValueError(f"log {name or '<root>'}: unknown format {_out.format}")
        if _out.to in STREAMS:
            _plan.append((_out.to, _out))
            continue
        if log_dir is None:
            raise ValueError(f"log {name or '<root>'}: {_out.to} needs a log dir")
        _file = Path(log_dir).resolve() / _out.to.replace(TIME_SLOT, Run_time())
        _plan.append((str(_file), _out))

    _own = [_r.target for _r in _DECLARED.get(name, [])]
    for _key, _out in _plan:
        _opened = _TARGETS.get(_key)
        _closing = _opened is not None and _opened in _own and _opened.users == 1   # 뗄 때 닫힐 자기 것
        _taken = [_o.format for _k, _o in _plan if _k == _key]
        if (_opened is not None and not _closing and _opened.format != _out.format) or len(set(_taken)) > 1:
            raise ValueError(f"log {name or '<root>'}: {_out.to} already written as another format")

    Detach(name)
    _logger = logging.getLogger(name)
    _logger.setLevel(_level)
    _routes: list[_Route] = []
    for _key, _out in _plan:
        if any(_r.target is _TARGETS.get(_key) for _r in _routes):
            continue
        _target = _TARGETS.get(_key) or _Open(_key, _out.format)
        _target.users += 1
        _route = _Route(name, _target)
        _logger.addHandler(_route)
        _routes.append(_route)
    _DECLARED[name] = _routes


def Detach(name: str) -> None:
    """logger 하나의 선언을 뗌. 아무도 안 쓰는 출력은 닫음. 걸린 선언이 없으면 아무것도 안 함.

    Args:
        name: logger 이름. root 는 `""`.
    """
    _routes = _DECLARED.pop(name, None)
    if _routes is None:
        return
    _logger = logging.getLogger(name)
    _logger.setLevel(logging.NOTSET if name else logging.WARNING)
    for _route in _routes:
        _logger.removeHandler(_route)
        _route.target.users -= 1
        if _route.target.users == 0:
            _route.target.handler.close()
            _TARGETS.pop(next(_k for _k, _t in _TARGETS.items() if _t is _route.target))


def _Open(key: str, format: str) -> _Target:
    """실제 출력 하나를 엶. 파일이면 폴더를 만들고 이어 씀."""
    if key in STREAMS:
        _handler: logging.Handler = logging.StreamHandler(STREAMS[key]())
    else:
        Path(key).parent.mkdir(parents=True, exist_ok=True)
        _handler = logging.FileHandler(key, encoding="utf-8")
    _handler.setFormatter(FORMATS[format]())
    _TARGETS[key] = _Target(_handler, format)
    return _TARGETS[key]


def _Nearest(name: str) -> str | None:
    """record 의 logger 이름에서 가장 가까운 선언 - 자기, 부모, ..., root(`""`). 없으면 None."""
    _name = name
    while True:
        if _name in _DECLARED:
            return _name
        if not _name:
            return None
        _name = _name.rpartition(".")[0]
