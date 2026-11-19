"""Structured logging primitives built on top of :class:`Data_Schema`."""
from __future__ import annotations
from enum import IntEnum
from dataclasses import dataclass, field, fields
from typing import Any, TypeVar, Literal, cast

from .data_schema import Data_Schema
from .system import Time_Utils


class Log_Level(IntEnum):
    """Severity levels used by :class:`Logger`."""
    TRA = 0  # Trace: 함수 진입/루프 등 매우 상세한 흐름
    DBG = 1  # Debug: 디버깅용 변수 상태 및 크기
    INF = 2  # Info: 일반적인 시스템 정상 작동 상태
    WRN = 3  # Warning: 경고성 이벤트 (무시 가능하나 주의 필요)
    ERR = 4  # Error: 에러 발생 (기능 일부 동작 실패)
    CRI = 5  # Critical: 시스템 종료 수준의 치명적 오류


@dataclass
class Log_Line(Data_Schema):
    """Base schema for a single log record.

    Attributes:
        level: Severity level stored as an integer literal from 0 to 5.
        timestamp: Creation time formatted as text.
        info: Free-form metadata that does not belong to explicit schema
            fields.
    """
    level: Literal[0, 1, 2, 3, 4, 5] = 2
    timestamp: str = field(
        default_factory=lambda: Time_Utils.Make_text_from()
    )
    info: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.level = cast(
            Literal[0, 1, 2, 3, 4, 5], max(0, min(self.level, 5))
        )

    def Format(self) -> str:
        """Formats the record for console output."""
        _level_name = Log_Level(self.level).name
        _info_str = ", ".join(f"{k}={v}" for k, v in self.info.items())
        return f"[{self.timestamp}] {_level_name} - {_info_str}"


LINE_TYPE = type[TypeVar("LINE", bound=Log_Line)] | None

@dataclass
class Logger(Data_Schema):
    """Collects and prints structured log records.

    Attributes:
        _default_type: Default log-line schema used when ``line_type`` is not
            provided.
        book: Stored log records in insertion order.
    """

    _default_type: type[Log_Line]
    book: list[Log_Line] = field(default_factory=list)

    def Print_to_console(self, line_num: int | list[int] | None = None) -> None:
        """Prints stored records to stdout.

        Args:
            line_num: Record index, index list, or ``None`` for all records.
        """
        if not self.book:
            return

        _targets = []
        if line_num is None:
            _targets = self.book
        elif isinstance(line_num, int):
            _targets = [self.book[line_num]]
        else:
            _targets = [self.book[i] for i in line_num if i < len(self.book)]

        for _line in _targets:
            print(_line.Format())

    def _Logging(self, level: Log_Level, line_type: LINE_TYPE, **kwarg) -> None:
        """Builds and stores a log line from keyword arguments."""
        _type = line_type or self._default_type

        if getattr(self, "_field_cache", None) is None:
            self._field_cache: dict[type, set[str]] = {}
            
        if _type not in self._field_cache:
            self._field_cache[_type] = {f.name for f in fields(_type)}
            
        _valid_fields = self._field_cache[_type]
        
        _init_args: dict[str, Any] = {"level": level.value}
        _info_dict: dict[str, Any] = {}

        for k, v in kwarg.items():
            if k == "info":
                if not isinstance(v, dict):
                    raise TypeError("'info'는 dict 타입이어야 함.")
                _info_dict.update(v)
            elif k in _valid_fields:
                _init_args[k] = v
            else:
                _info_dict[k] = v
                
        _init_args["info"] = _info_dict

        self.book.append(_type(**_init_args))

    def Trace(self, line_type: LINE_TYPE = None, **kwargs: Any) -> None:
        """Adds a trace-level log record."""
        self._Logging(Log_Level.TRA, line_type, **kwargs)

    def Debug(self, line_type: LINE_TYPE = None, **kwargs: Any) -> None:
        """Adds a debug-level log record."""
        self._Logging(Log_Level.DBG, line_type, **kwargs)

    def Info(self, line_type: LINE_TYPE = None, **kwargs: Any) -> None:
        """Adds an info-level log record."""
        self._Logging(Log_Level.INF, line_type, **kwargs)

    def Warning(self, line_type: LINE_TYPE = None, **kwargs: Any) -> None:
        """Adds a warning-level log record."""
        self._Logging(Log_Level.WRN, line_type, **kwargs)

    def Error(self, line_type: LINE_TYPE = None, **kwargs: Any) -> None:
        """Adds an error-level log record."""
        self._Logging(Log_Level.ERR, line_type, **kwargs)

    def Critical(self, line_type: LINE_TYPE = None, **kwargs: Any) -> None:
        """Adds a critical-level log record."""
        self._Logging(Log_Level.CRI, line_type, **kwargs)
