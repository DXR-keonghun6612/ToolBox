"""dataclass 직렬화 바탕 `Data_Schema`. 다른 모듈을 모름.

`Data_Schema` 는 저장용 dict(`Serialize`, 중첩 유지)와 호출용 dict(`Extract`, 평탄)를 가름.
중첩 dict 로 내려가는 걸음은 `Walk` 하나 - 규칙(`Walk_rule`)은 쓰는 쪽이 듦. 저장용은 `SERIALIZE`, 빈 규칙은 필드 이름 그대로.
규칙 상자는 클래스 속성(`__exclude_serialize__` 등) - 파생에서 MRO 로 합쳐짐(`__merge_specs__`).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any, ClassVar


@dataclass
class Data_Schema:
    """Dataclass mixin with serialization and flattened extraction helpers.

    Subclasses can customize behavior with class variables such as
    ``__exclude_serialize__``, ``__custom_keys__``, ``__exclude_extract__``,
    and ``__unpack_extract__``. These rule containers are merged across the
    MRO when a subclass is created.

    Attributes:
        __exclude_serialize__: Field names omitted from :meth:`Serialize`.
        __exclude_extract__: Field names omitted from :meth:`Extract`.
        __unpack_extract__: Dictionary fields unpacked into the extracted
            output.
        __custom_keys__: Output-key remapping used by :meth:`Serialize`.
        __custom_serializers__: Per-field serializer callbacks.
        __custom_extractors__: Per-field extractor callbacks.
        __merge_specs__: Registry describing which class-level containers are
            merged across subclasses.
    """

    __exclude_serialize__: ClassVar[set[str]] = set()
    __exclude_extract__: ClassVar[set[str]] = set()
    __unpack_extract__: ClassVar[set[str]] = set()

    __custom_keys__: ClassVar[dict[str, str]] = {}
    __custom_serializers__: ClassVar[dict[str, Callable[[Any], Any]]] = {}
    __custom_extractors__: ClassVar[dict[str, Callable[[Any], Any]]] = {}

    __merge_specs__: ClassVar[dict[str, type]] = {
        "__merge_specs__": dict,
        "__exclude_serialize__": set,
        "__exclude_extract__": set,
        "__unpack_extract__": set,
        "__custom_keys__": dict,
        "__custom_serializers__": dict,
        "__custom_extractors__": dict,
    }

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Merges registered rule containers from base classes into subclasses."""
        super().__init_subclass__(**kwargs)

        _merged_specs: dict[str, type] = {}
        for _base in reversed(cls.__mro__):
            _spec = getattr(_base, "__merge_specs__", None)
            if _spec:
                _merged_specs.update(_spec)
        cls.__merge_specs__ = _merged_specs

        for _name, _container in _merged_specs.items():
            if _name == "__merge_specs__":
                continue
            _merged = _container()
            for _base in reversed(cls.__mro__):
                _value = getattr(_base, _name, None)
                if _value is not None:
                    _merged.update(_value)
            setattr(cls, _name, _merged)

    def Serialize(self) -> dict[str, Any]:
        """저장용 중첩 dict - `SERIALIZE` 규칙의 `Walk`. 노드마다 `__exclude_serialize__`, `__custom_keys__`, `__custom_serializers__`."""
        return Walk(self, SERIALIZE)

    def Extract(self) -> dict[str, Any]:
        """Builds a flattened dictionary for runtime argument injection.

        Returns:
            A flattened dictionary extracted from the instance.
        """
        _res: dict[str, Any] = {}

        _cls = self.__class__
        _exclude = _cls.__exclude_extract__
        _extractors = _cls.__custom_extractors__
        _unpack = _cls.__unpack_extract__

        for _f in fields(self):
            if _f.name in _exclude:
                continue

            _value = getattr(self, _f.name)

            _extractor = _extractors.get(_f.name)
            if _extractor is not None:
                _res[_f.name] = _extractor(_value)
                continue

            if isinstance(_value, Data_Schema):
                _res.update(_value.Extract())
                continue

            if _f.name in _unpack and isinstance(_value, dict):
                if _value:
                    _res.update(_value)
                continue

            _res[_f.name] = _value

        return _res


@dataclass(frozen=True)
class Walk_rule:
    """`Walk` 의 규칙 - 노드 클래스에서 읽을 규칙 상자의 속성 이름. 이름이 None 이거나 노드에 그 속성이 없으면 그 규칙 없음.

    Attributes:
        skip: 뺄 칸 집합.
        keys: 칸 이름 -> 내놓을 key.
        values: 칸 이름 -> 값을 바꾸는 함수. 바꾼 값은 안으로 안 내려감.
        keep_container: list, tuple, set 꼴을 지키나. 아니면 list 로.
    """

    skip: str | None = None
    keys: str | None = None
    values: str | None = None
    keep_container: bool = False


#: 저장용 - `Serialize`.
SERIALIZE = Walk_rule(skip="__exclude_serialize__", keys="__custom_keys__", values="__custom_serializers__",
                      keep_container=True)


def Walk(value: Any, rule: Walk_rule) -> Any:
    """값을 중첩 dict 로 - `Data_Schema` 는 칸마다, dict 는 값마다, list · tuple · set 은 원소마다 내려감.

    규칙은 노드마다 그 노드 클래스의 규칙 상자 - 안쪽 노드는 안쪽 클래스의 것.
    """
    if isinstance(value, Data_Schema):
        _cls = type(value)
        _skip = _Rule_box(_cls, rule.skip, ())
        _keys = _Rule_box(_cls, rule.keys, {})
        _values = _Rule_box(_cls, rule.values, {})
        _out: dict[str, Any] = {}
        for _f in fields(value):
            if _f.name in _skip:
                continue
            _value = getattr(value, _f.name)
            _hook = _values.get(_f.name)
            _out[_keys.get(_f.name, _f.name)] = _hook(_value) if _hook is not None else Walk(_value, rule)
        return _out
    if isinstance(value, dict):
        return {_k: Walk(_v, rule) for _k, _v in value.items()}
    if isinstance(value, (list, tuple, set)):
        _items = [Walk(_v, rule) for _v in value]
        return type(value)(_items) if rule.keep_container else _items
    return value


def _Rule_box(cls: type, name: str | None, empty: Any) -> Any:
    """노드 클래스의 규칙 상자. 이름이 없거나 그 속성이 없으면 빈 것."""
    return getattr(cls, name, empty) if name else empty
