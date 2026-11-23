"""실행 단위의 설정 - 객체 하나의 설정 노드. 자기 기록 선언(`log`)과 정체성(`Identity`, `Hash`), 남은 설정과의 비교(`Diff`).

설정 트리는 재귀 - launcher 설정이 root, 그 아래 job, 그 아래 job 이 짓는 객체. 노드마다 같은 꼴.
정체성은 결과를 정하는 값 - 노드마다 자기 root 의 `__exclude_identity__` 칸만 뺌, 아래 노드는 그 노드의 규칙으로.
`config_type`, `object_type` 은 정체성 안 - 고른 클래스가 결과를 바꿈.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from typing import Any, ClassVar

from ..config import Base_Config
from ..schema import Data_Schema, Walk, Walk_rule
from .log import Log_Config

#: 정체성의 `Walk` 규칙 - 필드 이름 그대로, 노드마다 `__exclude_identity__` 를 뺌.
IDENTITY = Walk_rule(skip="__exclude_identity__")


@dataclass
class Unit_Config(Base_Config):
    """실행 단위 하나의 설정. 사용처가 상속해 자기 칸을 더함 - 더한 칸은 정체성.

    Attributes:
        log: 이 단위 logger 의 선언. 없으면 가장 가까운 위 선언을 따름.
    """

    log: Log_Config | None = None

    #: 정체성에서 빼는 이 노드 root 의 칸. 파생이 더하면 MRO 로 합쳐짐.
    __exclude_identity__: ClassVar[set[str]] = {"log"}
    __merge_specs__: ClassVar[dict[str, type]] = {"__exclude_identity__": set}

    def Identity(self) -> dict[str, Any]:
        """정체성 dict - `IDENTITY` 규칙의 `Walk`."""
        return Walk(self, IDENTITY)

    def Hash(self) -> str:
        """정체성의 sha256 hex. key 차례, 숫자 표기가 고정된 JSON 으로 잼 - 같은 정체성이면 같은 값."""
        _text = json.dumps(self.Identity(), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha256(_text.encode("utf-8")).hexdigest()


def Diff(saved: Any, current: Any, path: str = "") -> list[str]:
    """남은 설정(필드 이름 그대로 다시 읽은 dict)과 지금 값의 정체성이 다른 경로 목록.

    지금 값이 문서면 그 칸을 따라 내려감, 노드가 빼는 칸(`IDENTITY.skip`)은 건너뜀. dict, list 는 안쪽까지.
    남은 값에 있는 칸만 봄 - 나중에 더한 칸은 안 봄. 남은 값에 있는데 지금 없는 칸은 다름.
    """
    if isinstance(current, Data_Schema):
        if not isinstance(saved, dict):
            return [path or "<root>"]
        _skip = getattr(type(current), str(IDENTITY.skip), ())
        _names = {_f.name for _f in fields(current)}
        _out: list[str] = []
        for _k in sorted(saved, key=str):
            if _k in _skip:
                continue
            _p = f"{path}.{_k}" if path else str(_k)
            _out.extend(Diff(saved[_k], getattr(current, _k), _p) if _k in _names else [_p])
        return _out

    if isinstance(current, dict) and isinstance(saved, dict):
        _out = []
        for _k in sorted(saved, key=str):
            _p = f"{path}.{_k}" if path else str(_k)
            _out.extend(Diff(saved[_k], current[_k], _p) if _k in current else [_p])
        return _out

    if isinstance(current, (list, tuple)) and isinstance(saved, (list, tuple)):
        if len(saved) != len(current):
            return [path]
        return [_d for _i, (_s, _c) in enumerate(zip(saved, current)) for _d in Diff(_s, _c, f"{path}[{_i}]")]

    return [] if saved == current else [path]
