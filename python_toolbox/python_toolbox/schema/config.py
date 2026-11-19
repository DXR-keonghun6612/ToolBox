"""Config helpers built on top of :class:`python_toolbox.data_schema.Data_Schema`."""
from __future__ import annotations
import argparse
import types as _types
from dataclasses import dataclass, fields, MISSING
from pathlib import Path
from typing import Any, ClassVar, TypeVar, Union, get_type_hints, get_origin, get_args

from ..data_schema import Data_Schema
from ..registry import Registry
from ..file import Read_from, Write_to


@dataclass
class Base_Config(Data_Schema):
    """Schema base class with a file-writing convenience method.

    The class keeps config objects as ordinary :class:`Data_Schema` instances
    and only adds a small persistence entrypoint through :meth:`Write_to`.

    Attributes:
        config_type: Optional registry-facing type key stored with the config.
        object_type: Optional object category string stored with the config.
    """

    config_type: str = ""
    object_type: str = ""
    __exclude_extract__: ClassVar[set[str]] = {"config_type", "object_type"}

    def Write_to(
        self, name: str, save_dir: str | Path, encoding_type: str = "UTF-8"
    ) -> None:
        """Serializes the config and writes it to a file.

        Args:
            name: Output filename including suffix.
            save_dir: Directory that will contain the config file.
            encoding_type: Text encoding forwarded to the file writer.
        """
        Write_to(Path(save_dir) / name, self.Serialize(), encoding_type)


C_Type = TypeVar("C_Type", bound=Base_Config)


def Build_config(
    expected: type[C_Type],
    registry: Registry | None,
    meta: dict[str, Any] | None = None,
    **override: Any,
) -> C_Type:
    """meta 데이터와 override로부터 config 객체를 생성함.

    Args:
        expected: 반환 타입 제약. config_type이 없거나 registry가 None이면 직접 사용됨.
        registry: config class 조회에 사용할 레지스트리. None이면 expected를 직접 사용함.
        meta: config 초기값 딕셔너리. config_type 키로 registry에서 class를 결정함.
        **override: config 필드를 덮어쓸 공용 값. meta보다 우선 적용됨.

    Raises:
        KeyError: 레지스트리 조회 실패 시.
        TypeError: 조회된 타입이 expected와 불일치 시.
    """
    _meta = meta or {}
    _type_key = _meta.get("config_type", "")

    if registry is None or _type_key == "":
        _cfg = expected
    else:
        _cfg = registry.Get(_type_key, expected)

    _valid = {f.name for f in fields(_cfg)} & override.keys()
    return _cfg(**(_meta | {k: override[k] for k in _valid}))


def Build_config_from_file(
    expected: type[C_Type],
    registry: Registry | None,
    file_path: str | Path | None = None,
    **override: Any,
) -> C_Type:
    """파일 경로에서 meta를 로드한 뒤 Build_config를 호출함.

    Args:
        expected: 반환 타입 제약.
        registry: config class 조회에 사용할 레지스트리. None이면 expected를 직접 사용함.
        file_path: 로드할 config 파일 경로. None이거나 파일이 없으면 meta 없이 진행.
        **override: config 필드를 덮어쓸 공용 값.
    """
    _meta: dict[str, Any] = {}
    if file_path:
        _path = Path(file_path)
        if _path.exists():
            _is_ok, _loaded = Read_from(_path)
            if _is_ok and isinstance(_loaded, dict):
                _meta = _loaded

    return Build_config(expected, registry, _meta, **override)


def Build_parser_from_config(
    config_type: type[Base_Config],
    parser: argparse.ArgumentParser | None = None,
) -> argparse.ArgumentParser:
    """Builds an ``ArgumentParser`` from ``Base_Config`` fields.

    Args:
        config_type: Config class used as the parser schema.
        parser: Existing parser to extend. If omitted, a new parser is created.

    Returns:
        An ``ArgumentParser`` populated from dataclass fields.
    """
    if parser is None:
        parser = argparse.ArgumentParser()

    _hints = get_type_hints(config_type)
    _exclude = getattr(config_type, "__exclude_extract__", set())

    for f in fields(config_type):
        if f.name in _exclude:
            continue

        _type = _hints.get(f.name, str)
        _has_default = not (f.default is MISSING and f.default_factory is MISSING)  # type: ignore[misc]
        _default = (
            f.default if f.default is not MISSING
            else f.default_factory() if f.default_factory is not MISSING  # type: ignore[misc]
            else None
        )

        _origin = get_origin(_type)
        if _origin is Union or isinstance(_type, _types.UnionType):
            _inner = [a for a in get_args(_type) if a is not type(None)]
            _type = _inner[0] if _inner else str
            _origin = get_origin(_type)

        kwargs: dict[str, Any] = (
            {"default": _default} if _has_default else {"required": True}
        )

        if _type is bool:
            kwargs["action"] = argparse.BooleanOptionalAction
        elif _origin is list:
            _inner_args = get_args(_type)
            kwargs["type"] = _inner_args[0] if _inner_args else str
            kwargs["nargs"] = "*" if _has_default else "+"
        elif _origin is dict:
            kwargs["type"] = str
        else:
            kwargs["type"] = _type

        parser.add_argument(f"--{f.name}", **kwargs)

    return parser
