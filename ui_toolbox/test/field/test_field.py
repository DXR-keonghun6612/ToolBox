"""선언 - `Field.type` 판별 · 정렬 자리 · 행 다루기."""

from __future__ import annotations

from typing import Any

import pytest

from ui_toolbox.field._field import (
    Field,
    Order,
    Rows,
    list_pair,
    list_str,
    optional_float,
)


# ── 자료형 판별 ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tp, hit", [
    (list[str], True),
    (list[Any], True),
    (list[str] | None, True),
    (list[int], False),
    (list[tuple[str, str]], False),
    (str, False),
])
def test_list_str(tp, hit):
    assert list_str(tp) is hit


@pytest.mark.parametrize("tp, hit", [
    (list[tuple[str, str]], True),
    (list[tuple[str, str]] | None, True),
    (list[str], False),
    (list[tuple[str, int]], False),
])
def test_list_pair(tp, hit):
    assert list_pair(tp) is hit


@pytest.mark.parametrize("tp, hit", [
    (float | None, True),
    (float, False),
    (int | None, False),
    (float | int | None, False),
])
def test_optional_float(tp, hit):
    assert optional_float(tp) is hit


# ── 정렬 자리 ─────────────────────────────────────────────────────────────────
def test_order_puts_empty_last():
    assert sorted([None, "", 3, "a"], key=Order)[2:] == [None, ""]


def test_order_keeps_numbers_numeric():
    assert sorted([10, 9, 2], key=Order) == [2, 9, 10]


def test_order_keeps_text_alphabetic():
    assert sorted(["c", "a", "b"], key=Order) == ["a", "b", "c"]


def test_order_ranks_text_as_zero():
    """섞인 칸 - 글자는 수 `0` 자리. 양수보다 앞, 음수보다 뒤."""
    assert sorted([3, "a", -1], key=Order) == [-1, "a", 3]


# ── 행 ────────────────────────────────────────────────────────────────────────
def _rows() -> Rows:
    return Rows([Field("k"), Field("v")],
                [{"k": "a", "v": "1"}, {"k": "b", "v": "2"}, {"k": "c", "v": "3"}])


def test_set_reports_only_real_change():
    _r = _rows()
    assert _r.set(0, "k", "z") is True
    assert _r.set(0, "k", "z") is False


def test_rows_are_copies():
    _r = _rows()
    _r.rows()[0]["k"] = "깨짐"
    assert _r.get(0, "k") == "a"


def test_move_to_out_of_range_stays():
    _r = _rows()
    assert _r.move_to(0, 9) == 0
    assert [_x["k"] for _x in _r.rows()] == ["a", "b", "c"]


def test_move_to_reorders():
    _r = _rows()
    assert _r.move_to(0, 2) == 2
    assert [_x["k"] for _x in _r.rows()] == ["b", "c", "a"]


def test_matches_ignores_case_and_scans_every_column():
    _r = _rows()
    assert _r.matches(0, "A") is True
    assert _r.matches(0, "1") is True
    assert _r.matches(0, "없음") is False
    assert _r.matches(0, "") is True


@pytest.mark.parametrize("text, hit", [
    ("a?c", True),      # ? 는 딱 한 자
    ("a?bc", False),
    ("a*c", True),      # * 는 0 자 이상
    ("ac", False),      # 와일드카드 없이는 글자 그대로
    ("*bc*", True),
    ("a.c", False),     # 정규식 글자는 글자
    ("[abc]", False),
])
def test_matches_wildcards(text, hit):
    _r = Rows([Field("k")], [{"k": "xabcx"}])
    assert _r.matches(0, text) is hit


def test_title_falls_back_to_name():
    assert Field("k").title() == "k"
    assert Field("k", label="칸").title() == "칸"


# ── 보이는 글자 ───────────────────────────────────────────────────────────────
def _tag(value) -> str:
    return f"<{value}>"


def test_text_goes_through_display():
    assert (Field("k", display=_tag).text("a"), Field("k").text(3)) == ("<a>", "3")


def test_text_of_none_is_blank():
    """빈 값은 `display` 에 안 넘김 - 받는 쪽이 None 을 따로 안 막게."""
    assert Field("k", display=_tag).text(None) == ""


def test_matches_reads_the_shown_text():
    """보이는 글자로 거름. 선언 안 된 키는 화면에 없으므로 안 걸림."""
    _r = Rows([Field("k", display=_tag)], [{"k": "a", "숨음": "zz"}])
    assert (_r.matches(0, "<A>"), _r.matches(0, "zz")) == (True, False)
