"""읽은 설정 값의 공간 - 파일을 경로 key 로 펼쳐 한 표에 두고, argv 로 덮어쓰고, `${경로}` 를 풀어 설정을 지음.

경로는 `.` 로 이음. list 는 통째로 한 값 - index 경로 없음. `${경로}` 는 공간 root 기준 절대 경로만.
필드 타입이 설정(`X`, `X | None`, `list[X]`, `dict[str, X]`)이면 그 값도 설정으로 지음 - 필드 타입은 `get_type_hints` 로 읽음.
"""
from __future__ import annotations

import re
from dataclasses import MISSING, fields
from pathlib import Path
from types import UnionType
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

import yaml

from ..file import Read_from
from ..registry import Registry
from ..schema import Base_Config

C_Type = TypeVar("C_Type", bound=Base_Config)

#: 값 안의 `${경로}` 하나.
_REF = re.compile(r"\$\{([^${}]+)\}")


class Config_Space:
    """읽은 설정 값의 공간. 경로 -> 값 표 하나.

    Attributes:
        table: 펼친 경로 -> 값. 참조는 `${경로}` 문자열 그대로 - `Build` 때 풂.
    """

    def __init__(self) -> None:
        self.table: dict[str, Any] = {}
        self._schema: set[str] = set()

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

        for _key, _value in _Flatten(_data, at).items():
            self._Set(_key, _value)

    def Load_schema(self, cls: type[Base_Config], at: str = "") -> None:
        """설정 클래스의 기본값을 `at` 아래에 놓음 - 파일보다 먼저 까는 층. 선언된 필드는 파일에 없어도 덮어쓸 수 있게 됨.

        설정 객체를 만들지 않고 필드 정의만 읽음 - 기본값 없는 필드는 안 놓음.
        이 층에서만 온 값은 기억함 - registry 가 선언과 다른 클래스를 고른 자리에서는 빼고 지음(그 클래스의 기본값을 씀).
        """
        for _key, _value in _Flatten(_Defaults(cls), at).items():
            self._Set(_key, _value)
            self._schema.add(_key)

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
            if not self._Has(_key):
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
            ValueError: 참조 순환.
            TypeError: 설정 클래스에 없는 필드, registry 가 고른 타입이 `cls` 아님.
        """
        if at and not self._Has(at):
            raise KeyError(f"{at}: build path not in config space")

        _data = self._Resolve_path(at, []) if at else self._Resolve_tree("", [])
        return self._Make(cls, _data, at or "<root>", at, registry)

    def _Has(self, key: str) -> bool:
        """`key` 가 값이거나 하위 경로를 가짐."""
        _prefix = key + "."
        return key in self.table or any(_k.startswith(_prefix) for _k in self.table)

    def _Schema_only(self, key: str) -> bool:
        """`key` 와 그 아래 값이 모두 기본값 층에서만 옴."""
        _prefix = key + "."
        _keys = [_k for _k in self.table if _k == key or _k.startswith(_prefix)]
        return bool(_keys) and all(_k in self._schema for _k in _keys)

    def _Set(self, key: str, value: Any) -> None:
        """값 하나를 놓음. 그 경로 아래 하위 경로와 위쪽 값은 지움 - 값과 하위 경로가 함께 있지 않게."""
        _prefix = key + "."
        for _k in [_k for _k in self.table if _k.startswith(_prefix)]:
            del self.table[_k]
            self._schema.discard(_k)

        _parts = key.split(".")
        for _i in range(1, len(_parts)):
            _up = ".".join(_parts[:_i])
            self.table.pop(_up, None)
            self._schema.discard(_up)

        self.table[key] = value
        self._schema.discard(key)

    def _Make(
        self, cls: type[C_Type], data: Any, path: str, key: str, registry: Registry | None
    ) -> C_Type:
        """푼 dict 로 설정을 지음. 필드 타입이 설정이면 그 값도 재귀로 지음.

        registry 가 `cls` 와 다른 클래스를 고르면 기본값 층에서만 온 필드는 뺌 - `cls` 의 기본값이 그 클래스의 것을 가리지 않게.

        Args:
            path: 오류 메시지용 경로.
            key: 공간의 경로 - root 는 `""`.

        Raises:
            TypeError: dict 아님, 설정 클래스에 없는 필드, registry 가 고른 타입이 `cls` 아님.
            KeyError: registry 조회 실패.
        """
        if not isinstance(data, dict):
            raise TypeError(f"{path}: expected a mapping for {cls.__name__}, got {type(data).__name__}")

        _cls: type[C_Type] = cls
        _type_key = data.get("config_type", "")
        if registry is not None and _type_key:
            _cls = registry.Get(_type_key, cls)
        if _cls is not cls:
            data = {_n: _v for _n, _v in data.items() if not self._Schema_only(_Join(key, _n))}

        _hints = get_type_hints(_cls)
        _kwargs: dict[str, Any] = {}
        for _name, _value in data.items():
            _kwargs[_name] = self._Make_field(_hints.get(_name), _value, f"{path}.{_name}", _Join(key, _name), registry)

        try:
            return _cls(**_kwargs)
        except TypeError as _e:
            raise TypeError(f"{path}: {_e}") from None

    def _Make_field(self, hint: Any, value: Any, path: str, key: str, registry: Registry | None) -> Any:
        """필드 하나. 타입이 설정(`X`, `X | None`, `list[X]`, `dict[str, X]`)이면 지음, 아니면 값 그대로."""
        _origin = get_origin(hint)
        if _origin in (Union, UnionType):
            _args = [_a for _a in get_args(hint) if _a is not type(None)]
            if value is None or len(_args) != 1:
                return value
            hint, _origin = _args[0], get_origin(_args[0])

        if _origin is list and isinstance(value, list):
            _inner = get_args(hint)
            if _inner and _Is_config(_inner[0]):
                return [self._Make(_inner[0], _v, f"{path}[{_i}]", f"{key}[{_i}]", registry)
                        for _i, _v in enumerate(value)]
            return value

        if _origin is dict and isinstance(value, dict):
            _inner = get_args(hint)
            if len(_inner) == 2 and _Is_config(_inner[1]):
                return {_k: self._Make(_inner[1], _v, f"{path}.{_k}", _Join(key, _k), registry)
                        for _k, _v in value.items()}
            return value

        if _Is_config(hint):
            return self._Make(hint, value, path, key, registry)
        return value

    def _Resolve_path(self, key: str, stack: list[str]) -> Any:
        """경로 하나를 풂. 값이면 참조를 풀고, 하위 경로면 접은 dict."""
        if key in self.table:
            return self._Resolve_value(key, self.table[key], stack)
        if self._Has(key):
            return self._Resolve_tree(key, stack)
        raise KeyError(f"{key}: referenced path not in config space")

    def _Resolve_tree(self, key: str, stack: list[str]) -> dict[str, Any]:
        """`key` 아래 하위 경로를 모두 풀어 중첩 dict 로 접음."""
        _prefix = key + "." if key else ""
        _tree: dict[str, Any] = {}
        for _k in self.table:
            if not _k.startswith(_prefix):
                continue
            _node = _tree
            _parts = _k[len(_prefix):].split(".")
            for _p in _parts[:-1]:
                _node = _node.setdefault(_p, {})
            _node[_parts[-1]] = self._Resolve_value(_k, self.table[_k], stack)
        return _tree

    def _Resolve_value(self, key: str, value: Any, stack: list[str]) -> Any:
        """값 안의 `${경로}` 를 풂. 값 전체가 참조 하나면 대상 타입 그대로, 섞이면 문자열."""
        if not isinstance(value, str) or "${" not in value:
            return value

        if key in stack:
            raise ValueError(f"reference cycle: {' -> '.join(stack + [key])}")
        _stack = stack + [key]

        _whole = _REF.fullmatch(value)
        if _whole:
            return self._Resolve_path(_whole.group(1).strip(), _stack)

        return _REF.sub(
            lambda _m: str(self._Resolve_path(_m.group(1).strip(), _stack)), value
        )


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
        _out[_f.name] = _Plain(_value)
    return _out


def _Plain(value: Any) -> Any:
    """설정 객체를 필드 값 dict 로 - dict, list 안쪽까지."""
    if isinstance(value, Base_Config):
        return {_f.name: _Plain(getattr(value, _f.name)) for _f in fields(value)}
    if isinstance(value, dict):
        return {_k: _Plain(_v) for _k, _v in value.items()}
    if isinstance(value, list):
        return [_Plain(_v) for _v in value]
    return value


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
