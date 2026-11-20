"""실행 기록 - logger 마다 수준과 출력 위치를 정하는 표준 logging 설정. 기록하는 쪽은 `logging.getLogger(이름)` 만 씀.

출력 위치 : `console` 은 stderr, 나머지는 결과 자리 안의 파일 이름 - 형식은 확장자로(`.log` text, `.jsonl` JSON Lines).
따로 설정한 logger 는 `root` 출력으로 다시 흐르지 않음(`propagate=False`). 설정 안 한 logger 는 가장 가까운 설정된 부모를 따름.
"""
from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..schema import Base_Config

#: text 형식 한 줄.
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
#: 기본 text 기록 파일.
LOG_FILE = "run.log"
#: 기본 JSON Lines 기록 파일.
EVENT_FILE = "events.jsonl"
#: stderr 출력 위치 이름.
CONSOLE = "console"

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
#: 지난 `Setup_log` 가 건 (logger, handler) - 다시 부를 때 걷음.
_ATTACHED: list[tuple[logging.Logger, logging.Handler]] = []


@dataclass
class Log_Config(Base_Config):
    """logger 하나의 수준과 출력 위치.

    Attributes:
        level: 표준 수준 이름 - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
        to: 출력 위치 - `console` 또는 결과 자리 안의 `.log` / `.jsonl` 파일 이름.
    """

    level: str = "INFO"
    to: list[str] = field(default_factory=lambda: [CONSOLE])


def Default_log() -> dict[str, Log_Config]:
    """기본 기록 설정 - `root` 하나가 `INFO` 로 stderr, `LOG_FILE`, `EVENT_FILE` 에."""
    return {"root": Log_Config(level="INFO", to=[CONSOLE, LOG_FILE, EVENT_FILE])}


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


def Setup_log(result_dir: str | Path | None, log: Mapping[str, Log_Config]) -> None:
    """logger 마다 수준을 정하고 출력 위치의 handler 를 검. 지난번에 건 것은 닫고 바꿈 - 여러 번 불러도 겹치지 않음.

    Args:
        result_dir: 파일 출력 위치의 폴더. 파일 출력이 없으면 `None` 가능.
        log: logger 이름 -> 설정. `root` 는 root logger.

    Raises:
        ValueError: 모르는 수준, `console` 도 `.log` / `.jsonl` 도 아닌 출력 위치, 폴더 없이 파일 출력.
        FileNotFoundError: `result_dir` 이 없음.
    """
    _plan: list[tuple[logging.Logger, int, list[str]]] = []
    for _name, _cfg in log.items():
        _level = LEVELS.get(_cfg.level.upper())
        if _level is None:
            raise ValueError(f"log.{_name}.level: unknown log level {_cfg.level}")
        for _to in _cfg.to:
            if _to != CONSOLE and Path(_to).suffix not in (".log", ".jsonl"):
                raise ValueError(f"log.{_name}.to: {_to} is neither '{CONSOLE}' nor a .log / .jsonl file")
            if _to != CONSOLE and result_dir is None:
                raise ValueError(f"log.{_name}.to: {_to} needs a result dir")
        _logger = logging.getLogger() if _name == "root" else logging.getLogger(_name)
        _plan.append((_logger, _level, list(_cfg.to)))

    if result_dir is not None and not Path(result_dir).is_dir():
        raise FileNotFoundError(f"{result_dir}: result dir not found")

    _Detach()
    _handlers: dict[str, logging.Handler] = {}
    for _logger, _level, _targets in _plan:
        _logger.setLevel(_level)
        if _logger is not logging.getLogger():
            _logger.propagate = False
        for _to in _targets:
            if _to not in _handlers:
                _handlers[_to] = _Make_handler(_to, result_dir)
            _logger.addHandler(_handlers[_to])
            _ATTACHED.append((_logger, _handlers[_to]))


def _Make_handler(to: str, result_dir: str | Path | None) -> logging.Handler:
    """출력 위치 하나의 handler."""
    if to == CONSOLE:
        _handler: logging.Handler = logging.StreamHandler(sys.stderr)
        _handler.setFormatter(logging.Formatter(TEXT_FORMAT))
        return _handler
    _handler = logging.FileHandler(Path(result_dir) / to, encoding="utf-8")  # type: ignore[arg-type]
    _handler.setFormatter(Json_formatter() if to.endswith(".jsonl") else logging.Formatter(TEXT_FORMAT))
    return _handler


def _Detach() -> None:
    """지난 `Setup_log` 가 건 handler 를 떼고 닫음. 따로 설정했던 logger 는 수준, propagate 를 되돌림."""
    _closed: set[int] = set()
    for _logger, _handler in _ATTACHED:
        _logger.removeHandler(_handler)
        if _logger is not logging.getLogger():
            _logger.setLevel(logging.NOTSET)
            _logger.propagate = True
        if id(_handler) not in _closed:
            _handler.close()
            _closed.add(id(_handler))
    _ATTACHED.clear()
