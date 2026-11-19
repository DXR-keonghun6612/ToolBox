"""style 객체 -> QSS. style 객체는 `selector -> 속성 맵`.

- 덮기 - 받은 것 위에 node 의 것, 같은 selector 의 같은 속성은 node 의 것
- selector 의 맨 이름이 node key 면 `#key`. node key 이면서 클래스 이름이면 실패
"""

from __future__ import annotations

import re
from typing import Any

from ._find import Is_class

__all__ = ["Cascade", "Sheet"]

#: style selector 의 맨 이름.
_NAME = re.compile(r"[^\W\d]\w*")


def Cascade(up: dict, own: Any, where: str) -> dict:
    """받은 style 위에 node 의 것을 덮은 사본.

    Raises:
        TypeError: style 이 `selector -> 속성 맵` 이 아닐 때.
    """
    if not isinstance(own, dict):
        raise TypeError(f"{where}.style: expected selector -> property map - got {type(own).__name__}")
    _out = {_s: dict(_p) for _s, _p in up.items()}
    for _sel, _props in own.items():
        if not isinstance(_sel, str) or not isinstance(_props, dict):
            raise TypeError(f"{where}.style.{_sel}: expected property map - got {_props!r}")
        _out[_sel] = {**_out.get(_sel, {}), **_props}
    return _out


def _simple(piece: str, keys: set[str]) -> str:
    """단순 selector 하나 - 맨 이름이 node key 면 `#key`.

    Raises:
        KeyError: 맨 이름이 node key 이면서 클래스 이름일 때.
    """
    _m = _NAME.match(piece)
    if _m is None or _m.group() not in keys:
        return piece
    if Is_class(_m.group()):
        raise KeyError(f"style selector {_m.group()!r} is both a node key and a class name")
    return "#" + piece


def _selector(text: str, keys: set[str]) -> str:
    """selector 글자 - 공백, `,`, `>`, `+`, `~` 로 갈린 단순 selector 마다 `_simple`. `[]`, `()`, 따옴표 안은 안 가름."""
    _out: list[str] = []
    _piece = ""
    _depth = 0
    _quote = ""
    for _ch in text:
        if _quote:
            _quote = "" if _ch == _quote else _quote
        elif _ch in "\"'":
            _quote = _ch
        elif _ch in "[(":
            _depth += 1
        elif _ch in "])":
            _depth -= 1
        elif _depth == 0 and (_ch.isspace() or _ch in ",>+~"):
            _out += [_simple(_piece, keys), _ch]
            _piece = ""
            continue
        _piece += _ch
    _out.append(_simple(_piece, keys))
    return "".join(_out)


def Sheet(style: dict, keys: set[str]) -> str:
    """style 객체 -> QSS. 맨 이름이 `keys` 에 있으면 `#key`.

    Raises:
        KeyError: selector 의 맨 이름이 node key 이면서 클래스 이름일 때.
    """
    return "\n".join(
        f"{_selector(_sel, keys)} {{ {' '.join(f'{_k}: {_v};' for _k, _v in _props.items())} }}"
        for _sel, _props in style.items())
