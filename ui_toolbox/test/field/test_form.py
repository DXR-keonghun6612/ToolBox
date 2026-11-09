"""폼 - 자료형마다 위젯이 서고, 못 짓는 자료형은 드러남.

값이 안 실리면 소비처가 기본값으로 도므로, 조용히 넘기는 것이 가장 나쁜 결과.
"""

from __future__ import annotations

import pytest

from ui_toolbox.field import Config_form, Field

_SPECS = [
    Field("flag", bool, True),
    Field("count", int, 3, min=0, max=10),
    Field("ratio", float, 0.5, min=0.0, max=1.0, step=0.1),
    Field("name", str, "짓기"),
    Field("tags", list[str], ["p", "q"]),
    Field("limit", float | None, None, min=0.0, max=1.0, step=0.1),
    Field("pairs", list[tuple[str, str]], [("k", "v")]),
]


def test_every_declared_type_gets_a_widget():
    _form = Config_form(_SPECS)
    assert set(_form.get()) == {_s.name for _s in _SPECS}


def test_defaults_round_trip():
    _got = Config_form(_SPECS).get()
    assert _got["flag"] is True
    assert _got["count"] == 3
    assert _got["ratio"] == pytest.approx(0.5)
    assert _got["name"] == "짓기"
    assert _got["tags"] == ["p", "q"]
    assert _got["limit"] is None
    assert _got["pairs"] == [("k", "v")]


def test_unknown_type_raises():
    """조용히 버리면 config 에 안 실려 기본값으로 돎."""
    with pytest.raises(TypeError):
        Config_form([Field("blob", dict)])


def test_unknown_kind_raises():
    """선언한 kind 를 말없이 무시하면 사람이 부탁한 위젯이 아닌 것이 섬."""
    with pytest.raises(TypeError):
        Config_form([Field("who", str, kind="없는변형")])


def test_kind_picks_a_different_widget():
    from ui_toolbox.field.form.widget import Path_row, Text_row
    _form = Config_form([Field("plain", str, "a"),
                         Field("file", str, "b", kind="path")])
    assert isinstance(_form._widgets["plain"], Text_row)
    assert isinstance(_form._widgets["file"], Path_row)


def test_readonly_field_gets_a_readout():
    from ui_toolbox.field.form.widget import Readout_row
    _form = Config_form([Field("n", int, 5, editable=False)])
    _w = _form._widgets["n"]
    assert isinstance(_w, Readout_row)
    assert _form.get()["n"] == 5          # 자료형이 안 상함


def test_readout_never_reports_an_edit():
    _form = Config_form([Field("n", int, 5, editable=False)])
    _fired: list = []
    _form.params_changed.connect(lambda: _fired.append(True))
    _form.load({"n": 9})
    assert (_fired, _form.get()["n"]) == ([], 9)


def test_load_restores_without_signal():
    _form = Config_form(_SPECS)
    _fired: list = []
    _form.params_changed.connect(lambda: _fired.append(True))
    _form.load({"count": 8, "ratio": 0.9, "name": "복원", "tags": ["z"],
                "flag": False, "limit": 0.4})
    assert _fired == []
    _got = _form.get()
    assert _got["count"] == 8
    assert _got["ratio"] == pytest.approx(0.9)
    assert _got["name"] == "복원"
    assert _got["tags"] == ["z"]
    assert _got["flag"] is False
    assert _got["limit"] == pytest.approx(0.4)


def test_load_ignores_unknown_key():
    _form = Config_form(_SPECS)
    _form.load({"없는칸": 1})
    assert _form.get()["count"] == 3


def test_human_edit_emits():
    _form = Config_form(_SPECS)
    _fired: list = []
    _form.params_changed.connect(lambda: _fired.append(True))
    _form._widgets["count"]._slider.setValue(6)
    assert len(_fired) == 1
