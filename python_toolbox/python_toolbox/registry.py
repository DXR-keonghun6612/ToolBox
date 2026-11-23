"""이름 -> 클래스, Callable 등록표. 잘못된 상속, Callable 시그니처 불일치를 등록 시점에 막음."""
from __future__ import annotations
from typing import Any, TypeVar, Generic, Callable, get_origin, get_args, cast, overload
import inspect
import collections.abc


T = TypeVar("T")
C = TypeVar("C")
C_Type = TypeVar("C_Type")


class Registry(Generic[T]):
    """Registers classes or callables with lightweight runtime validation."""

    def __init__(self, name: str, target_type: Any) -> None:
        """Initializes the registry.

        Args:
            name: Human-readable registry name used in error messages.
            target_type: Target class or ``Callable`` signature.

        Raises:
            TypeError: If ``target_type`` is neither a class nor a callable
                signature.
        """
        self.name = name
        self.target_type = target_type
        self._module_dict: dict[str, T] = {}

        self._is_callable_target = (
            get_origin(self.target_type) is collections.abc.Callable
        )
        self._expected_param_count = -1

        if self._is_callable_target:
            _args = get_args(self.target_type)
            if _args and _args[0] is not ...:
                self._expected_param_count = len(_args[0])
        elif not isinstance(self.target_type, type):
            raise TypeError(
                f"[ERROR] 지원하지 않는 target_type: {self.target_type}"
            )

    @overload
    def Get(self, key: str) -> T: ...
    @overload
    def Get(self, key: str, expected: type[C_Type]) -> type[C_Type]: ...

    def Get(self, key: str, expected: type | None = None) -> Any:
        """Returns the registered object for a key.

        Args:
            key: Registered name.
            expected: Optional base type used for class validation.

        Returns:
            The registered object.

        Raises:
            KeyError: If ``key`` is not registered.
            TypeError: If ``expected`` is provided and the object is not a
                subclass of it.
        """
        if key not in self._module_dict:
            raise KeyError(f"'{key}'은(는) {self.name}에 등록되지 않았음.")

        _data = self._module_dict[key]

        if expected is None:
            return _data

        if inspect.isclass(_data) and issubclass(_data, expected):
            return cast(type, _data)

        raise TypeError(
            f"'{key}'은(는) '{expected.__name__}'의 하위 클래스가 아님."
        )

    def Register_module(self, name: str | None = None) -> Callable[[C], C]:
        """Creates a decorator that registers an object.

        Args:
            name: Explicit registration key. If omitted, the object's lowercase
                ``__name__`` is used.

        Returns:
            A decorator that registers the target object and returns it.

        Raises:
            TypeError: If the object does not match the registry mode or fails
                inheritance/signature checks.
            ValueError: If a name cannot be inferred.
            KeyError: If the key is already registered.
        """
        def _register(obj: C) -> C:
            _obj_is_type = inspect.isclass(obj)
            _obj_is_callable = callable(obj)

            _for_callable = self._is_callable_target

            if _obj_is_type == _for_callable:
                _target_name = "Callable" if _for_callable else "Class"
                raise TypeError(
                    f"[ERROR] '{getattr(obj, '__name__', obj)}'은(는) "
                    f"레지스트리 목적({_target_name} 전용)과 일치하지 않음."
                )

            if _obj_is_type:
                if not issubclass(obj, self.target_type):
                    raise TypeError(
                        f"'{obj.__name__}'은(는) "
                        f"'{self.target_type.__name__}'의 하위 클래스여야 함."
                    )

            elif _obj_is_callable:
                if self._expected_param_count >= 0:
                    _sig = inspect.signature(obj)
                    _actual_params = [
                        _p for _p in _sig.parameters.values()
                        if _p.kind in (
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            inspect.Parameter.POSITIONAL_ONLY,
                        )
                    ]
                    if len(_actual_params) != self._expected_param_count:
                        raise TypeError(
                            f"[ERROR] 파라미터 개수 불일치. "
                            f"요구됨: {self._expected_param_count}개, "
                            f"실제: {len(_actual_params)}개."
                        )
            else:
                raise TypeError(
                    f"[ERROR] '{obj}'은(는) 지원하지 않는 객체 타입임."
                )

            _name = name or getattr(
                obj, "__name__", getattr(obj.__class__, "__name__", "")
            ).lower()
            if _name == "<lambda>" or not _name:
                raise ValueError(
                    "이름을 추론할 수 없거나 람다 함수임. "
                    "name 파라미터를 명시할 것."
                )

            if _name in self._module_dict:
                raise KeyError(
                    f"'{_name}'은(는) 이미 {self.name}에 등록됨."
                )

            self._module_dict[_name] = cast(T, obj)
            return obj

        return _register
