"""칸 선언과 그 값들, 그리고 `Field.type` 판별.

칸 하나가 이름 · 자료형 · 표시 · 입력 힌트를 함께 든다. 행이 하나든 여럿이든 이 선언이 같고,
무엇으로 보이는지만 표현이 정한다 - 한 행이면 폼, 여러 행이면 표.
"""

from __future__ import annotations

import re
import types
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Union, get_args, get_origin

__all__ = ["Field", "Order", "Pattern", "Rows", "Type_name", "list_pair", "list_str",
           "optional_float"]


def Order(value: Any) -> tuple[int, float, str]:
    """정렬 자리 - 빈 값은 뒤로, 수는 수끼리, 나머지는 글자로.

    섞인 자료형이 한 칸에 오므로 `(빈 값인가, 수, 글자)` 로 잰다.
    """
    if value is None or value == "":
        return (1, 0.0, "")
    if isinstance(value, (bool, int, float)):
        return (0, float(value), "")
    return (0, 0.0, str(value))


@dataclass(frozen=True)
class Field:
    """칸 하나 선언.

    Attributes:
        name: 행 dict 에서 이 칸이 읽고 쓰는 이름.
        type: 파이썬 타입. 어느 위젯으로 고칠지의 근거.
        default: 값이 없을 때 앉힐 것.
        label: 사람에게 보일 문구. 비면 `name`.
        tip: 툴팁.
        width: 폭(px). 표에서는 비율 - 칸 폭의 합이 표 폭을 따름. `0` 이면 선언된 폭의 평균.
        editable: 사람이 고칠 수 있나.
        min: 수 입력의 하한.
        max: 수 입력의 상한.
        step: 수 입력의 증감 단위.
        kind: 입력 변형 이름 (`path` 등). 같은 자료형이라도 위젯이 갈릴 때.
        display: 값 -> 보일 글자. 비면 `str`. 정렬은 값으로, 필터링은 이 글자로.
    """

    name:     str
    type:     Any = str
    default:  Any = None
    label:    str = ""
    tip:      str = ""
    width:    int = 0
    editable: bool = True
    min:      float | None = None
    max:      float | None = None
    step:     float | None = None
    kind:     str = ""
    display:  Callable[[Any], str] | None = None

    def title(self) -> str:
        """머리글에 쓸 문구."""
        return self.label or self.name

    def text(self, value: Any) -> str:
        """그 값의 보일 글자. 빈 값은 `display` 에 안 넘기고 빈 글자."""
        if value is None:
            return ""
        return str(value) if self.display is None else self.display(value)


# ── Field.type 판별 ───────────────────────────────────────────────────────────
def _strip_optional(tp):
    """`X | None` 이면 `X`, 아니면 그대로."""
    _origin = get_origin(tp)
    _is_union = _origin is Union or (
        hasattr(types, "UnionType") and isinstance(tp, types.UnionType))
    if not _is_union:
        return tp
    # nullable 목록도 목록 위젯을 받게 한다 - 위젯이 안 생기면 그 값이 통째로 유실된다
    _rest = [_a for _a in get_args(tp) if _a is not type(None)]
    return _rest[0] if len(_rest) == 1 else tp


def list_str(tp) -> bool:
    """`list[str]` · `list[Any]` 인가 (Optional 포함)."""
    _tp = _strip_optional(tp)
    return get_origin(_tp) is list and get_args(_tp) in ((str,), (Any,))


def list_pair(tp) -> bool:
    """`list[tuple[str, str]]` 인가 (Optional 포함)."""
    _tp = _strip_optional(tp)
    return get_origin(_tp) is list and get_args(_tp) == (tuple[str, str],)


def optional_float(tp) -> bool:
    """`float | None` 인가."""
    _origin = get_origin(tp)
    _is_union = _origin is Union or (
        hasattr(types, "UnionType") and isinstance(tp, types.UnionType))
    return _is_union and set(get_args(tp)) == {float, type(None)}


#: 그 자체로 판별되는 자료형. 순서가 없어 dict 하나면 됨.
_PLAIN = {bool: "bool", int: "int", float: "float", str: "str"}


def Type_name(tp) -> str:
    """`Field.type` -> 등록표가 쓰는 이름. 모르는 자료형이면 빈 글자.

    겹침이 있어 순서가 있다 - `float | None` 은 `float` 보다 먼저 걸러야 한다.
    """
    if optional_float(tp):
        return "optional_float"
    if list_pair(tp):
        return "list_pair"
    if list_str(tp):
        return "list_str"
    return _PLAIN.get(tp, "")


class Rows:
    """칸 선언 + 그 값을 든 행들.

    표현을 모른다. 바뀐 것을 알리는 일도 안 한다 - 표현이 자기 신호로 낸다.
    """

    def __init__(self, fields: list[Field], rows: list[dict] | None = None) -> None:
        """Args:
        fields: 칸 선언. 순서가 곧 표시 순서.
        rows: 초기 행들 (사본을 든다).
        """
        self._fields = list(fields)
        self._rows: list[dict] = [dict(_r) for _r in (rows or [])]

    @property
    def fields(self) -> list[Field]:
        """칸 선언."""
        return self._fields

    def rows(self) -> list[dict]:
        """지금 행들 (사본)."""
        return [dict(_r) for _r in self._rows]

    def __len__(self) -> int:
        return len(self._rows)

    def valid(self, at: int) -> bool:
        """`at` 이 있는 자리인가."""
        return 0 <= at < len(self._rows)

    # ── 값 ────────────────────────────────────────────────────────────────────
    def get(self, at: int, name: str) -> Any:
        """`at` 행의 `name` 칸 값 (없으면 None)."""
        return self._rows[at].get(name) if self.valid(at) else None

    def set(self, at: int, name: str, value: Any) -> bool:
        """`at` 행의 `name` 칸을 고친다.

        Returns:
            실제로 바뀌었으면 True. 같은 값이면 False - 표현이 헛되이 신호를 안 내게.
        """
        if not self.valid(at) or self._rows[at].get(name) == value:
            return False
        self._rows[at][name] = value
        return True

    # ── 수명 · 순서 ───────────────────────────────────────────────────────────
    def insert(self, at: int, row: dict | None = None) -> int:
        """`at` 자리에 행을 끼우고 그 자리를 낸다 (범위 밖이면 끝에)."""
        _at = min(max(0, at), len(self._rows))
        self._rows.insert(_at, dict(row or {}))
        return _at

    def append(self, row: dict | None = None) -> int:
        """끝에 행을 붙이고 그 자리를 낸다."""
        return self.insert(len(self._rows), row)

    def remove(self, at: int) -> bool:
        """`at` 행을 뺀다 (범위 밖이면 False)."""
        if not self.valid(at):
            return False
        del self._rows[at]
        return True

    def move_to(self, at: int, to: int) -> int:
        """`at` 행을 `to` 자리로 옮기고 새 자리를 낸다 (못 옮기면 제자리)."""
        # 임의 자리로 떨어뜨리는 것이 정본. 드래그앤드롭이 붙을 때 더할 것이 없도록
        if not self.valid(at) or not self.valid(to):
            return at
        self._rows.insert(to, self._rows.pop(at))
        return to

    def move(self, at: int, step: int) -> int:
        """`at` 행을 `step` 칸 옮기고 새 자리를 낸다."""
        return self.move_to(at, at + step)

    def replace(self, rows: list[dict] | None) -> None:
        """행 전체를 갈아끼운다."""
        self._rows = [dict(_r) for _r in (rows or [])]

    def matches(self, at: int, text: str) -> bool:
        """그 행의 어느 칸이든 보이는 글자가 `text` 를 품고 있나 (대소문자 무시).

        선언 안 된 키는 화면에 없으므로 안 봄.

        Args:
            at: 행 자리.
            text: 찾는 글자. `*` 는 0 자 이상, `?` 는 한 자. 비면 늘 True.
        """
        if not text:
            return True
        _pat = Pattern(text)
        _row = self._rows[at]
        return any(_pat.search(_f.text(_row.get(_f.name))) for _f in self._fields)


@lru_cache(maxsize=8)
def Pattern(text: str) -> re.Pattern:
    """필터링 글자 -> 정규식. 부분 일치, 대소문자 무시. `*` 는 0 자 이상, `?` 는 한 자.

    행마다 다시 짓지 않게 캐시 - 한 번 거를 때 행 수만큼 불림.
    """
    _src = re.escape(text).replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(_src, re.IGNORECASE | re.DOTALL)
