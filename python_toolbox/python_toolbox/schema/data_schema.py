"""Base schema utilities for serialization and flattened extraction."""
from __future__ import annotations
from dataclasses import dataclass, fields
from typing import Any, Callable, ClassVar


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
        """Builds a nested dictionary representation for persistence.

        Returns:
            A serialized dictionary representation of the instance.
        """
        _res: dict[str, Any] = {}

        _cls = self.__class__
        _exclude = _cls.__exclude_serialize__
        _keys = _cls.__custom_keys__
        _serializers = _cls.__custom_serializers__

        for _f in fields(self):
            if _f.name in _exclude:
                continue

            _value = getattr(self, _f.name)
            _key = _keys.get(_f.name, _f.name)

            _serializer = _serializers.get(_f.name)
            if _serializer is not None:
                _res[_key] = _serializer(_value)
                continue

            _res[_key] = self._serialize_value(_value)

        return _res

    def _serialize_value(self, value: Any) -> Any:
        """Serializes a single value recursively."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, Data_Schema):
            return value.Serialize()

        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}

        if isinstance(value, (list, tuple, set)):
            return type(value)(self._serialize_value(item) for item in value)

        return value

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
