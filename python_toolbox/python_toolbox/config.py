"""설정 - 설정의 부모 `Base_Config` 와, 설정 파일 · 덮어쓰기에서 설정을 짓는 공간 `Config_Space`.

`Base_Config` 는 dict 로 초기화만 - 파일, argv 를 모름. 읽고 짓는 것은 `Config_Space`.
공간은 파일을 경로 key 로 펼쳐 한 표에 두고, argv 로 덮어쓰고, `${경로}` 를 풀어 설정을 지음.
경로는 `.` 로 이음. list 는 통째로 한 값 - index 경로 없음. `${경로}` 는 공간 root 기준 절대 경로만.
필드 타입이 설정(`X`, `X | None`, `list[X]`, `dict[str, X]`)이면 그 값도 설정으로 지음 - 필드 타입은 `get_type_hints` 로 읽음.
"""
from __future__ import annotations

import re
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from types import UnionType
from typing import (
    Any, ClassVar, TypeVar, Union, cast, get_args, get_origin, get_type_hints,
)

import yaml

from .file import Read_from
from .registry import Registry
from .schema import Data_Schema, Walk, Walk_rule


@dataclass
class Base_Config(Data_Schema):
    """설정의 부모. dict 로 초기화만 - 파일, argv 를 모름.

    Attributes:
        config_type: registry 에서 하위 설정 클래스를 고르는 key.
        object_type: 설정과 함께 저장하는 객체 종류 이름.
    """

    config_type: str = ""
    object_type: str = ""
    __exclude_extract__: ClassVar[set[str]] = {"config_type", "object_type"}


C_Type = TypeVar("C_Type", bound=Base_Config)

#: 값 안의 `${경로}` 하나.
_REF = re.compile(r"\$\{([^${}]+)\}")


class Config_Space:
    """읽은 설정 값의 공간. 경로 -> 값 표 하나 - 참조는 `${경로}` 글 그대로 두고 읽을 때(`Get`, `Build`) 풂."""

    def __init__(self) -> None:
        self._table: dict[str, Any] = {}
        self._schema: set[str] = set()

    def Get(self, at: str = "", *, _stack: tuple[str, ...] = ()) -> Any:
        """`at` 의 값 - 참조를 푼 것. 하위 경로가 있으면 접은 dict. 비면 root 전체.

        Args:
            at: 읽을 경로.
            _stack: 참조를 따라온 경로 - 순환 검사. 바깥에서는 안 줌.

        Raises:
            KeyError: 공간에 없는 경로, 참조한 경로 없음.
            ValueError: 참조 순환.
        """
        if at in self._table:
            return self._Resolve_value(at, self._table[at], _stack)
        _keys = self._Under(at)
        if at and not _keys:
            raise KeyError(f"{at}: path not in config space")

        _prefix = at + "." if at else ""
        _tree: dict[str, Any] = {}
        for _k in _keys:
            _node = _tree
            _parts = _k[len(_prefix):].split(".")
            for _p in _parts[:-1]:
                _node = _node.setdefault(_p, {})
            _node[_parts[-1]] = self._Resolve_value(_k, self._table[_k], _stack)
        return _tree

    def Load(self, path: str | Path, at: str = "") -> None:
        """설정 파일을 펼쳐 `at` 아래에 놓음. 같은 경로는 덮어씀.

        Args:
            path: 설정 파일 경로. 확장자로 형식을 고름.
            at: 놓을 경로. 비면 root.

        Raises:
            FileNotFoundError: 파일 없음.
            ValueError: 못 읽음, 최상위가 dict 아님, key 안에 `.`.
        """
        _path = Path(path)
        if not _path.is_file():
            raise FileNotFoundError(f"{_path}: config file not found")

        _ok, _data = Read_from(_path)
        if not _ok or not isinstance(_data, dict):
            raise ValueError(f"{_path}: cannot read a mapping")
        self._Put(_data, at, schema=False)

    def Load_schema(self, cls: type[Base_Config], at: str = "") -> None:
        """설정 클래스의 기본값을 `at` 아래에 놓음 - 파일보다 먼저 까는 층. 선언된 필드는 파일에 없어도 덮어쓸 수 있게 됨.

        설정 객체를 만들지 않고 필드 정의만 읽음 - 기본값 없는 필드는 안 놓음.
        이 층에서만 온 값은 기억함 - registry 가 선언과 다른 클래스를 고른 자리에서는 빼고 지음(그 클래스의 기본값을 씀).
        """
        self._Put(_Defaults(cls), at, schema=True)

    def Override(self, dotlist: list[str]) -> None:
        """argv 의 `a.b=값` 들로 덮어씀. 값은 YAML 스칼라 규칙으로 읽음(`50` -> int, `true` -> bool).

        Args:
            dotlist: `경로=값` 문자열 목록.

        Raises:
            ValueError: `=` 없음.
            KeyError: 공간에 없는 경로 - 새 key 를 만들지 않음.
        """
        for _item in dotlist:
            _key, _sep, _raw = _item.partition("=")
            if not _sep or not _key:
                raise ValueError(f"{_item}: expected 'path=value'")
            if not self._Under(_key):
                raise KeyError(f"{_key}: override path not in config space")
            self._Set(_key, yaml.safe_load(_raw))

    def Build(
        self, cls: type[C_Type], at: str = "", registry: Registry | None = None
    ) -> C_Type:
        """`at` 아래의 값을 풀어 설정 하나를 지음.

        Args:
            cls: 지을 설정 클래스. registry 가 고른 클래스의 기대 타입.
            at: 설정이 놓인 경로. 비면 root.
            registry: 있으면 `config_type` 값으로 하위 클래스를 고름.

        Raises:
            KeyError: `at` 이 공간에 없음, 참조한 경로 없음, registry 조회 실패.
            ValueError: 참조 순환, registry 없이 `config_type` 이 적힘.
            TypeError: dict 아님, 설정 클래스에 없는 필드, registry 가 고른 타입이 `cls` 아님.
        """
        return cast(C_Type, self._Build(cls, self.Get(at), at, registry))

    def _Under(self, key: str) -> list[str]:
        """표에서 `key` 자신과 그 아래 경로. root(`""`)는 전부."""
        if not key:
            return list(self._table)
        _prefix = key + "."
        return [_k for _k in self._table if _k == key or _k.startswith(_prefix)]

    def _Put(self, data: dict[str, Any], at: str, schema: bool) -> None:
        """중첩 dict 를 `at` 아래 경로로 펼쳐 하나씩 놓음. `schema` 면 기본값 층으로 기억."""
        for _key, _value in _Flatten(data, at).items():
            self._Set(_key, _value)
            if schema:
                self._schema.add(_key)

    def _Set(self, key: str, value: Any) -> None:
        """값 하나를 놓음. 그 경로와 아래 경로, 위쪽 값은 지움 - 값과 하위 경로가 함께 있지 않게."""
        for _k in self._Under(key):
            del self._table[_k]
            self._schema.discard(_k)

        _parts = key.split(".")
        for _i in range(1, len(_parts)):
            _up = ".".join(_parts[:_i])
            self._table.pop(_up, None)
            self._schema.discard(_up)

        self._table[key] = value
        self._schema.discard(key)

    def _Build(self, hint: Any, value: Any, key: str, registry: Registry | None) -> Any:
        """annotation `hint` 에 맞춰 값 하나를 지음 - `X | None` 은 벗기고, `list[X]` · `dict[str, X]` 는 원소마다,
        설정 클래스는 칸마다. 그 밖은 값 그대로.

        설정 클래스 : registry 가 `config_type` 으로 다른 클래스를 고르면 기본값 층에서만 온 칸은 뺌 -
        선언 클래스의 기본값이 고른 클래스의 것을 가리지 않게.

        Args:
            key: 공간의 경로 - root 는 `""`. 오류 메시지에도 씀.

        Raises:
            TypeError: 설정 자리에 dict 아님, 설정 클래스에 없는 칸, registry 가 고른 타입이 `hint` 아님.
            KeyError: registry 조회 실패.
            ValueError: registry 없이 `config_type` 이 적힘 - 고를 수 없는 하위 클래스.
        """
        _origin = get_origin(hint)
        if _origin in (Union, UnionType):
            _args = [_a for _a in get_args(hint) if _a is not type(None)]
            if value is None or len(_args) != 1:
                return value
            hint, _origin = _args[0], get_origin(_args[0])

        if _origin in (list, dict) and isinstance(value, _origin):
            _inner = get_args(hint)
            _item = _inner[-1] if _inner else None   # list[X], dict[str, X] 의 X
            if not _Is_config(_item):
                return value
            if isinstance(value, list):
                return [self._Build(_item, _v, f"{key}[{_i}]", registry) for _i, _v in enumerate(value)]
            return {_k: self._Build(_item, _v, _Join(key, _k), registry) for _k, _v in value.items()}

        if not _Is_config(hint):
            return value

        _where = key or "<root>"
        if not isinstance(value, dict):
            raise TypeError(f"{_where}: expected a mapping for {hint.__name__}, got {type(value).__name__}")

        _cls = hint
        _type_key = value.get("config_type", "")
        if _type_key and registry is None:
            raise ValueError(f"{_where}: config_type '{_type_key}' given but no registry to pick it")
        if registry is not None and _type_key:
            _cls = registry.Get(_type_key, hint)
        if _cls is not hint:
            value = {_n: _v for _n, _v in value.items()
                     if not ((_keys := self._Under(_Join(key, _n))) and all(_k in self._schema for _k in _keys))}

        _hints = get_type_hints(_cls)
        _kwargs = {_n: self._Build(_hints.get(_n), _v, _Join(key, _n), registry) for _n, _v in value.items()}
        try:
            return _cls(**_kwargs)
        except TypeError as _e:
            raise TypeError(f"{_where}: {_e}") from None

    def _Resolve_value(self, key: str, value: Any, stack: tuple[str, ...]) -> Any:
        """값 안의 `${경로}` 를 풂. 값 전체가 참조 하나면 대상 타입 그대로, 섞이면 문자열."""
        if not isinstance(value, str) or "${" not in value:
            return value

        if key in stack:
            raise ValueError(f"reference cycle: {' -> '.join((*stack, key))}")
        _stack = (*stack, key)

        _whole = _REF.fullmatch(value)
        if _whole:
            return self.Get(_whole.group(1).strip(), _stack=_stack)

        return _REF.sub(lambda _m: str(self.Get(_m.group(1).strip(), _stack=_stack)), value)


def _Join(key: str, name: str) -> str:
    """공간 경로 잇기 - root 는 `""`."""
    return f"{key}.{name}" if key else name


def _Is_config(hint: Any) -> bool:
    """`hint` 가 설정 클래스."""
    return isinstance(hint, type) and issubclass(hint, Base_Config)


def _Defaults(cls: type[Base_Config]) -> dict[str, Any]:
    """설정 클래스 필드의 기본값 dict. 기본값이 설정 객체면 그 필드 값으로 펼침."""
    _out: dict[str, Any] = {}
    for _f in fields(cls):
        if _f.default is not MISSING:
            _value = _f.default
        elif _f.default_factory is not MISSING:
            _value = _f.default_factory()
        else:
            continue
        _out[_f.name] = Walk(_value, Walk_rule())   # 공간은 필드 이름이 key
    return _out


def _Flatten(data: dict[str, Any], at: str) -> dict[str, Any]:
    """중첩 dict 를 `at` 아래 경로 key 로 펼침. 빈 dict 는 값 하나로 남김."""
    _flat: dict[str, Any] = {}
    for _key, _value in data.items():
        _name = str(_key)
        if "." in _name:
            raise ValueError(f"{at}.{_name}: key must not contain '.'")
        _path = f"{at}.{_name}" if at else _name
        if isinstance(_value, dict) and _value:
            _flat.update(_Flatten(_value, _path))
        else:
            _flat[_path] = _value
    return _flat
