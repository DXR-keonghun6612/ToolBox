"""묶음 - key -> 객체. container 마다 셋(`items`, `link`, `action`)."""

from __future__ import annotations

from typing import Any

__all__ = ["Names"]


class Names:
    """key -> 객체 묶음. 속성으로 접근(`page.items.records`), 경로로 찾음(`find("records.table")`). 같은 key 를 두 번 넣으면 실패."""

    def __init__(self) -> None:
        self.__dict__["_keys"] = []

    def put(self, key: str, value: Any, where: str = "") -> None:
        """key 로 넣음. `where` 는 실패 글자에 붙일 자리.

        Raises:
            KeyError: 이미 있는 key 일 때, 묶음의 메서드 이름(`put`, `keys`, `find`)과 겹칠 때.
        """
        if key in self.__dict__ or hasattr(type(self), key):
            raise KeyError(f"{where}: duplicate key or Names method name {key!r}")
        self.__dict__[key] = value
        self._keys.append(key)

    def keys(self) -> list[str]:
        """넣은 차례의 key."""
        return list(self._keys)

    def find(self, path: str) -> Any:
        """`.` 으로 이은 key 경로의 객체. segment 마다 그 객체의 `items` 로 들어감.

        Raises:
            KeyError: 없는 key 일 때, 중간 segment 가 container 가 아닐 때.
        """
        _parts = path.split(".")
        _names = self
        for _at, _part in enumerate(_parts):
            if _part not in _names._keys:
                raise KeyError(f"{path!r}: no key {_part!r} - have {_names._keys}")
            _obj = _names.__dict__[_part]
            if _at == len(_parts) - 1:
                return _obj
            _names = getattr(_obj, "items", None)
            if not isinstance(_names, Names):
                raise KeyError(f"{path!r}: {'.'.join(_parts[:_at + 1])} is not a container")
        raise KeyError(f"empty path {path!r}")

    def __setattr__(self, key: str, value: Any) -> None:
        raise AttributeError("use put() - it checks duplicates")
