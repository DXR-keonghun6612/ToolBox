"""칸 선언 -> 위젯 등록표.

`(자료형 이름, kind, editable)` 하나가 위젯 하나를 가리킴. 자료형이 늘 때 고치는 자리가
여기 한 곳이 되도록, 짓는 쪽이 자기를 올리고 폼은 찾기만 함.

값 위젯은 선언을 모르므로([`value/`](value)) 여기가 그 사이를 이음 - `Field` 에서 인자를
꺼내는 것은 이 파일만 함.

라벨은 키가 아니라 빌드 인자. 세로 폼은 위젯이 이름을 달고, 머리줄이 있는 스택은 안 담.

틀린 것은 올릴 때 막음. 찾을 때 터지면 그 자리를 누가 올렸는지 못 앎.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from PySide6.QtWidgets import QWidget

from ..._field import Field, Type_name
from .value import (
    Check_row,
    Float_slider_row,
    Int_slider_row,
    List_row,
    Optional_float_row,
    Path_row,
    Readout_row,
    Text_row,
)

__all__ = ["Build", "Register"]

#: `(자료형 이름, kind, editable)` -> `(칸 선언, 라벨)` 을 받아 위젯을 내는 것.
_TABLE: dict[tuple[str, str, bool], Callable[[Field, str], QWidget]] = {}


def Register(type_name: str, kind: str = "", editable: bool = True):
    """그 자리에 설 위젯을 올리는 데코레이터.

    Args:
        type_name: `Type_name` 이 내는 이름.
        kind: `Field.kind`. 같은 자료형이라도 위젯이 갈릴 때.
        editable: `Field.editable`.

    Raises:
        ValueError: 이름 없는 것(람다)일 때. 어느 것이 섰는지 못 적음.
        TypeError: 인자가 `(칸 선언, 라벨)` 둘이 아닐 때.
        KeyError: 이미 찬 자리일 때.
    """
    def _add(make: Callable[[Field, str], QWidget]) -> Callable[[Field, str], QWidget]:
        _name = getattr(make, "__name__", "")
        if not _name or _name == "<lambda>":
            raise ValueError("이름 없는 것은 못 올림 - 이름 있는 함수로 적을 것")

        _params = [_p for _p in inspect.signature(make).parameters.values()
                   if _p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                  inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        if len(_params) != 2:
            raise TypeError(f"'{_name}' 은 인자가 `(칸 선언, 라벨)` 둘이어야 함 "
                            f"(지금 {len(_params)}개)")

        _key = (type_name, kind, editable)
        if _key in _TABLE:
            raise KeyError(f"이미 찬 자리: {_key} - '{_TABLE[_key].__name__}'")
        _TABLE[_key] = make
        return make
    return _add


def Build(spec: Field, labelled: bool = True) -> QWidget | None:
    """그 칸에 설 위젯. 자리가 비었으면 `None` - 부르는 쪽이 드러냄.

    Args:
        spec: 칸 선언.
        labelled: 위젯이 칸 이름을 스스로 다나. 머리줄이 이름을 이미 들면 끔.
    """
    _make = _TABLE.get((Type_name(spec.type), spec.kind, spec.editable))
    return None if _make is None else _make(spec, spec.title() if labelled else "")


def _range(spec: Field) -> tuple[float, float, float]:
    """수 입력의 하한 · 상한 · 단위. 선언이 비운 자리는 여기 기본."""
    return (0 if spec.min is None else spec.min,
            100 if spec.max is None else spec.max,
            0.05 if spec.step is None else spec.step)


def _decimals(spec: Field, step: float) -> int:
    """실수 입력의 소수 자릿수. 선언이 비우면 `step` 의 자릿수, 둘째 자리 아래로는 안 내려감."""
    if spec.decimals is not None:
        return spec.decimals
    _text = f"{step:.10f}".rstrip("0")
    return max(2, len(_text.split(".")[1]) if "." in _text else 0)


# ── 고칠 수 있는 칸 ───────────────────────────────────────────────────────────
@Register("bool")
def _check(spec: Field, label: str) -> QWidget:
    return Check_row(label, bool(spec.default), tooltip=spec.tip)


@Register("int")
def _int(spec: Field, label: str) -> QWidget:
    _min, _max, _ = _range(spec)
    return Int_slider_row(label, int(_min), int(_max),
                          int(spec.default or 0), tooltip=spec.tip)


@Register("float")
def _float(spec: Field, label: str) -> QWidget:
    _min, _max, _step = _range(spec)
    return Float_slider_row(label, _min, _max, float(spec.default or 0.0),
                            step=_step, decimals=_decimals(spec, _step), tooltip=spec.tip)


@Register("optional_float")
def _optional_float(spec: Field, label: str) -> QWidget:
    _min, _max, _step = _range(spec)
    return Optional_float_row(label, _min, _max, spec.default,
                              step=_step, decimals=_decimals(spec, _step), tooltip=spec.tip)


@Register("str")
def _text(spec: Field, label: str) -> QWidget:
    return Text_row(label, spec.default, tooltip=spec.tip)


@Register("str", kind="path")
def _path(spec: Field, label: str) -> QWidget:
    _row = Path_row(label, mode="file", tooltip=spec.tip)
    _row.set_value(spec.default)
    return _row


@Register("list_str")
def _list(spec: Field, label: str) -> QWidget:
    return List_row(label, spec.default, tooltip=spec.tip)


# ── 못 고치는 칸 ──────────────────────────────────────────────────────────────
def _readout(spec: Field, label: str) -> QWidget:
    """자료형을 안 가림. 보이는 꼴은 `style.py` 의 READOUT 역할."""
    return Readout_row(label, spec.default, tooltip=spec.tip, display=spec.display)


for _name in ("bool", "int", "float", "optional_float", "str", "list_str",
              "list_pair"):
    for _kind in ("", "path"):
        Register(_name, kind=_kind, editable=False)(_readout)
