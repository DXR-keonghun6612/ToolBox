"""설정 - 설정의 부모 `Base_Config`, 설정 클래스 등록표 `CONFIGS`, meta 를 들고 설정을 짓는 `Config_Space`.

meta 는 중첩 dict 하나 - 처음 dict, root 설정 파일들을 차례로 겹치고 argv 를 덮은 것. 기본값은 채우지 않음, 없는 칸은 dataclass 기본값.
값 자리의 `file@<경로>` 는 그 파일 내용, `config@<등록 이름>` 은 `{config_type: <등록 이름>}` - 읽을 때 펼쳐 그 자리 값을 바꿈.
파일 지정은 `file@` 경로만 - 이름으로 고르는 묶음(config group) 없음.
`file@` 상대 경로 - 파일 안은 그 파일의 폴더, 처음 dict 는 생성자의 `folder`, argv 는 cwd.
경로는 `.` 로 이음, list 안은 경로 없음. `${경로}` 는 meta root 기준, 지을 때 풂 - meta 에 적힌 값만 가리킴.
공용 값 자리 없음 - 참조는 다른 설정의 경로를 바로 지목.
YAML flow list(`[${a}]`) 안의 참조는 `{` 때문에 못 읽음 - block list 나 따옴표로.
검사는 지을 때 설정 객체가 스스로 - meta 에 넣을 때는 안 봄.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields
from functools import cache
from pathlib import Path
from types import UnionType
from typing import Any, ClassVar, TypeVar, Union, get_args, get_origin, get_type_hints

import yaml

from .file import Read_from
from .registry import Registry
from .schema import Data_Schema

#: 기본 타입 검사 - 칸 타입 -> 받는 값 타입.
_ACCEPT: dict[type, tuple[type, ...]] = {int: (int,), float: (int, float), str: (str,), bool: (bool,)}
#: 값 안의 `${경로}` 하나.
_REF = re.compile(r"\$\{([^${}]+)\}")
#: 값 자리에서 파일 내용으로 펼치는 접두어.
FILE_PREFIX = "file@"
#: 값 자리에서 등록 이름의 설정으로 펼치는 접두어.
CONFIG_PREFIX = "config@"


@dataclass
class Base_Config(Data_Schema):
    """설정의 부모. 생성 때 칸의 기본 타입을 검사 - 하위 클래스의 `__post_init__` 은 `super().__post_init__()` 을 부름.

    Attributes:
        config_type: `CONFIGS` 에서 이 노드의 클래스를 고르는 key.
        object_type: 설정과 함께 저장하는 객체 종류 이름.

    Raises:
        TypeError: `None` 을 안 받는 칸에 `None`. 단순 타입(`int`, `float`, `str`, `bool`, 그 `| None`) 칸의 값 타입이 다름.
            `float` 칸은 `int` 도, `int` 칸은 `bool` 도 받음.
    """

    config_type: str = ""
    object_type: str = ""
    __exclude_extract__: ClassVar[set[str]] = {"config_type", "object_type"}

    def __post_init__(self) -> None:
        for _name, (_type, _optional) in self.Fields().items():
            _value = getattr(self, _name)
            if _value is None:
                if not _optional:
                    raise TypeError(f"{_name}: got None, field is not optional")
                continue
            if _type in _ACCEPT and not isinstance(_value, _ACCEPT[_type]):
                raise TypeError(f"{_name}: expected {_type.__name__}, got {type(_value).__name__}")

    @classmethod
    @cache
    def Fields(cls) -> dict[str, tuple[Any, bool]]:
        """칸 -> `(실제 타입, None 허용)`. `X | None` 은 `X` 로 벗김, 갈래가 둘 이상이면 annotation 그대로. `Any` 는 None 허용.

        칸 annotation 만 벗김 - list 원소의 `None` 은 자리 값이라 그대로. cache key 는 클래스.
        """
        _hints = get_type_hints(cls)
        _out: dict[str, tuple[Any, bool]] = {}
        for _f in fields(cls):
            _hint = _hints[_f.name]
            if get_origin(_hint) in (Union, UnionType):
                _args = [_a for _a in get_args(_hint) if _a is not type(None)]
                _optional = len(_args) < len(get_args(_hint))
                _out[_f.name] = (_args[0] if len(_args) == 1 else _hint, _optional)
            else:
                _out[_f.name] = (_hint, _hint is Any)
        return _out

    @classmethod
    def From_dict(cls: type[C_Type], data: Any, at: str = "") -> C_Type:
        """dict 하나로 지음 - 칸 타입(`X`, `list[X]`, `dict[str, X]`)을 따라 안쪽 설정까지. 설정 아닌 칸은 값 그대로.

        `config_type` 이 있으면 `CONFIGS` 에서 고름 - `cls` 의 하위여야 함. 없으면 `cls`.

        Args:
            data: 지을 노드.
            at: 오류 메시지의 경로.

        Raises:
            KeyError: `config_type` 이 `CONFIGS` 에 없음.
            TypeError: dict 아님, 고른 클래스가 `cls` 의 하위 아님, 모르는 칸, 칸 값 타입이 다름.
        """
        _where = at or "<root>"
        if not isinstance(data, dict):
            raise TypeError(f"{_where}: expected a mapping for {cls.__name__}, got {type(data).__name__}")
        _key = data.get("config_type")
        _cls = CONFIGS.Get(_key, cls) if _key else cls
        _fields = _cls.Fields()
        _kwargs = {
            _n: Base_Config._Value(_fields[_n][0] if _n in _fields else None, _v, f"{at}.{_n}" if at else _n)
            for _n, _v in data.items()
        }
        try:
            return _cls(**_kwargs)
        except TypeError as _e:
            raise TypeError(f"{_where}: {_e}") from _e

    @staticmethod
    def _Value(hint: Any, value: Any, at: str) -> Any:
        """칸 값 하나를 칸 타입에 맞춰 지음 - 설정 칸은 `From_dict`, list, dict 는 원소마다."""
        if value is None:
            return None
        _origin = get_origin(hint)
        if _origin in (list, dict) and isinstance(value, _origin):
            _item = get_args(hint)[-1] if get_args(hint) else None
            if not (isinstance(_item, type) and issubclass(_item, Base_Config)):
                return value
            if isinstance(value, list):
                return [Base_Config._Value(_item, _v, f"{at}[{_i}]") for _i, _v in enumerate(value)]
            return {_k: Base_Config._Value(_item, _v, f"{at}.{_k}") for _k, _v in value.items()}
        if isinstance(hint, type) and issubclass(hint, Base_Config):
            return hint.From_dict(value, at)
        return value


C_Type = TypeVar("C_Type", bound=Base_Config)

#: 설정 클래스 등록표 - `config_type` 값 -> 클래스. 모든 사용처가 한 표 - key 가 겹치면 등록 때 실패.
CONFIGS = Registry[type[Base_Config]]("config", Base_Config)


class Config_Space:
    """meta 하나 - root 설정 파일들을 차례로 겹치고 argv 를 덮음. 참조는 글 그대로 두고 읽을 때(`Get`, `Build`) 풂."""

    def __init__(self, meta: dict[str, Any] | None = None, folder: str | Path | None = None) -> None:
        """Args:
            meta: 처음 meta - 파일 없이 dict 하나로 지을 때. 펼침은 `Load` 와 같음.
            folder: `meta` 안 `file@` 상대 경로의 기준 - 그 dict 를 적은 파일의 폴더. 비면 cwd.
        """
        self._meta: dict[str, Any] = {}
        if meta is not None:
            self._Overlay(self._meta, meta, Path(folder) if folder is not None else Path.cwd(), frozenset())

    def Load(self, path: str | Path) -> None:
        """root 설정 파일 하나를 meta 에 겹침 - dict 는 안쪽까지, 그 밖은 바꿈. 확장자로 형식을 고름.

        Raises:
            FileNotFoundError: 파일 없음, 펼친 `file@` 의 파일 없음.
            ValueError: 못 읽음, 최상위가 dict 아님, 지원 안 하는 확장자, `file@` 순환.
            KeyError: `config@` 의 등록 이름이 `CONFIGS` 에 없음.
        """
        _data = self._Expand(f"{FILE_PREFIX}{path}", Path.cwd(), frozenset())
        self._Overlay(self._meta, _data, Path.cwd(), frozenset())

    def Override(self, dotlist: list[str]) -> None:
        """`경로=값` 들로 차례로 그 자리 값을 바꿈. 값은 YAML 스칼라 규칙(`50` -> int, `true` -> bool). 검사는 지을 때.

        중간 dict 는 없으면 만듦. `file@` 의 상대 경로는 cwd 기준.

        Raises:
            ValueError: `=` 없음, 경로 빔, 중간 경로가 값, `Load` 의 펼침 오류.
            FileNotFoundError, KeyError: `Load` 의 펼침 오류.
        """
        for _item in dotlist:
            _key, _sep, _raw = _item.partition("=")
            if not _sep or not _key:
                raise ValueError(f"{_item}: expected 'path=value'")
            _parts = _key.split(".")
            _node = self._meta
            for _part in _parts[:-1]:
                _node = _node.setdefault(_part, {})
                if not isinstance(_node, dict):
                    raise ValueError(f"{_key}: '{_part}' holds a value, not a mapping")
            _node[_parts[-1]] = self._Expand(yaml.safe_load(_raw), Path.cwd(), frozenset())

    def Get(self, at: str = "") -> Any:
        """`at` 의 값에서 `${경로}` 를 푼 사본. 비면 meta 전체.

        값 전체가 참조 하나면 대상 그대로, 섞이면 글. 참조한 값 안의 참조도 풂. list 는 원소마다 - 순번 경로는 없음.

        Raises:
            KeyError: `at` 이나 참조한 경로 없음.
            ValueError: 참조 순환.
        """
        def _Value(value: Any, stack: tuple[str, ...]) -> Any:
            if isinstance(value, dict):
                return {_k: _Value(_v, stack) for _k, _v in value.items()}
            if isinstance(value, list):
                return [_Value(_v, stack) for _v in value]
            if not isinstance(value, str) or "${" not in value:
                return value
            _whole = _REF.fullmatch(value)
            if _whole:
                return _Target(_whole.group(1).strip(), stack)
            return _REF.sub(lambda _m: str(_Target(_m.group(1).strip(), stack)), value)

        def _Target(path: str, stack: tuple[str, ...]) -> Any:
            if path in stack:
                raise ValueError(f"reference cycle: {' -> '.join((*stack, path))}")
            return _Value(self._At(path), (*stack, path))

        return _Value(self._At(at), (at,) if at else ())

    def Build(self, at: str, expected: type[C_Type]) -> C_Type:
        """`at` 의 설정 하나를 지음 - 참조를 풀고 `expected.From_dict`. 클래스는 그 노드의 `config_type` - 따로 짓는 노드는 꼭 가짐.

        Args:
            at: 지을 노드의 경로. 비면 meta 전체.
            expected: 고른 클래스가 그 하위여야 하는 클래스.

        Raises:
            KeyError, ValueError: `Get` 그대로.
            ValueError: `config_type` 이 빔.
            KeyError: `config_type` 이 `CONFIGS` 에 없음.
            TypeError: dict 아님, 고른 클래스가 기대의 하위 아님, 모르는 칸, 칸 값 타입이 다름.
        """
        _data = self.Get(at)
        _where = at or "<root>"
        if not isinstance(_data, dict):
            raise TypeError(f"{_where}: expected a mapping, got {type(_data).__name__}")
        if not _data.get("config_type"):
            raise ValueError(f"{_where}: config_type is empty")
        return expected.From_dict(_data, at)

    def _At(self, at: str) -> Any:
        """meta 의 `at` 값 - 참조 그대로. 비면 meta 전체.

        Raises:
            KeyError: 경로 없음.
        """
        _node: Any = self._meta
        for _part in at.split(".") if at else []:
            if not isinstance(_node, dict) or _part not in _node:
                raise KeyError(f"{at}: path not in meta")
            _node = _node[_part]
        return _node

    @staticmethod
    def _Overlay(base: dict[str, Any], over: dict[str, Any], folder: Path, seen: frozenset[Path]) -> dict[str, Any]:
        """`over` 를 펼쳐 `base` 에 겹침 - dict 는 안쪽까지, 그 밖(펼친 `file@`, `config@` 포함)은 바꿈.

        Args:
            folder: `file@` 상대 경로의 기준.
            seen: 지금 펼치는 파일들 - 순환 확인.
        """
        for _key, _value in over.items():
            if isinstance(_value, dict):
                _node = base.get(_key)
                if not isinstance(_node, dict):
                    _node = base[_key] = {}
                Config_Space._Overlay(_node, _value, folder, seen)
            else:
                base[_key] = Config_Space._Expand(_value, folder, seen)
        return base

    @staticmethod
    def _Expand(value: Any, folder: Path, seen: frozenset[Path]) -> Any:
        """값 하나를 펼침 - `file@` 는 그 파일 내용(안쪽도 펼침), `config@` 는 `{config_type: 이름}`. dict, list 는 안쪽까지."""
        if isinstance(value, dict):
            return Config_Space._Overlay({}, value, folder, seen)
        if isinstance(value, list):
            return [Config_Space._Expand(_v, folder, seen) for _v in value]
        if not isinstance(value, str):
            return value

        if value.startswith(FILE_PREFIX):
            _path = (folder / value[len(FILE_PREFIX):]).resolve()
            if _path in seen:
                raise ValueError(f"{_path}: file reference cycle")
            if not _path.is_file():
                raise FileNotFoundError(f"{_path}: config file not found")
            _ok, _data = Read_from(_path)
            if not _ok or not isinstance(_data, dict):
                raise ValueError(f"{_path}: cannot read a mapping")
            return Config_Space._Overlay({}, _data, _path.parent, seen | {_path})
        if value.startswith(CONFIG_PREFIX):
            _name = value[len(CONFIG_PREFIX):]
            CONFIGS.Get(_name)
            return {"config_type": _name}
        return value
