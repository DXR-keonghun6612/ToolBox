"""table 칸 선언 - 검사, 값 검사, 보일 글자, 정렬 자리.

칸 선언은 dict 하나 - `name`, `type`, `editable`, `open`, `width`(폭 비율, 양의 정수). yaml 설정이 줌.
"""

from __future__ import annotations

from typing import Any

__all__ = ["TYPES", "Blank", "Check_columns", "Check_value", "Order", "Text"]

#: `type` 이름 -> 값의 파이썬 타입.
TYPES: dict[str, type] = {"bool": bool, "int": int, "float": float, "str": str}

#: 빠지면 실패하는 키.
_REQUIRED = ("name", "type")

#: 빠지면 그 값으로 채우는 키.
_OPTIONAL: dict[str, Any] = {"editable": False, "open": None, "width": None}


def Check_columns(columns: list[dict]) -> list[dict]:
    """칸 선언을 검사하고 빠진 선택 키를 채운 사본.

    Args:
        columns: 칸 선언. 차례가 곧 보이는 차례.

    Raises:
        ValueError: 키가 빠지거나 모를 때, `name` 이 겹칠 때, `type` 을 모를 때.
        TypeError: `editable` 이 bool 이 아닐 때, `open` 이 글자가 아닐 때, `width` 가 양의 정수가 아닐 때.
    """
    _out: list[dict] = []
    _seen: set[str] = set()
    for _at, _col in enumerate(columns):
        _missing = [_k for _k in _REQUIRED if _k not in _col]
        if _missing:
            raise ValueError(f"column {_at}: missing keys {_missing}")
        _unknown = set(_col) - set(_REQUIRED) - set(_OPTIONAL)
        if _unknown:
            raise ValueError(f"column {_col['name']!r}: unknown keys {sorted(_unknown)}")
        if _col["name"] in _seen:
            raise ValueError(f"duplicate column name {_col['name']!r}")
        if _col["type"] not in TYPES:
            raise ValueError(f"column {_col['name']!r}: unknown type {_col['type']!r} - "
                             f"known {list(TYPES)}")
        _full = {**_OPTIONAL, **_col}
        if not isinstance(_full["editable"], bool):
            raise TypeError(f"column {_col['name']!r}: editable must be bool - got {_full['editable']!r}")
        if _full["open"] is not None and not isinstance(_full["open"], str):
            raise TypeError(f"column {_col['name']!r}: open must be a region name - got {_full['open']!r}")
        _w = _full["width"]
        if _w is not None and (type(_w) is not int or _w <= 0):
            raise TypeError(f"column {_col['name']!r}: width must be a positive int - got {_w!r}")
        _seen.add(_col["name"])
        _out.append(_full)
    return _out


def Check_value(column: dict, value: Any) -> None:
    """값이 칸 `type` 과 맞나. None 은 빈칸이라 늘 맞음.

    타입은 정확히 같아야 함 - bool 은 int 칸에 안 들어감. 예외는 float 칸의 int - yaml, JSON 이 `1.0` 을 `1` 로 적음.

    Raises:
        TypeError: 어긋날 때.
    """
    if value is None:
        return
    _want = TYPES[column["type"]]
    if type(value) is not _want and not (_want is float and type(value) is int):
        raise TypeError(f"column {column['name']!r} is {column['type']} - "
                        f"got {value!r} ({type(value).__name__})")


def Text(column: dict, value: Any) -> str:
    """값 -> 보일 글자. None 은 빈 글자."""
    return "" if value is None else str(value)


def Blank(column: dict) -> Any:
    """그 칸 타입의 빈 값 - `False`, `0`, `0.0`, `""`."""
    return TYPES[column["type"]]()


def Order(column: dict, value: Any) -> tuple[bool, Any]:
    """값 -> 정렬 열쇠. None 은 뒤로 - 그 칸 타입의 빈 값으로 바꿔 넣음(None 끼리 비교하면 에러).

    한 칸에는 타입 하나 - `Check_value` 가 막음.
    """
    if value is None:
        return (True, Blank(column))
    return (False, value)
