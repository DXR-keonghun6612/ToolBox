"""글자 control - 비면 None, 목록 가르기, 경로 갈래와 대화상자 시작 폴더 흐름.

시작 폴더 : 대화상자는 마지막 경로의 폴더에서 열림 - state. 경로가 파일이면 그 폴더, 디렉터리면 그 자리.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from ui_toolbox.component.control._text import List_text, Path_text, Paths_text, Str_text


def test_text_flow(tmp_path):
    # 단계 : 입력을 마칠 때만 냄 - 치는 동안, 글자가 그대로인 마침은 안 냄
    _s = Str_text("a")
    _got: list = []
    _s.value_changed.connect(_got.append)
    QTest.keyClicks(_s, "bc")
    assert _got == [], "Str_text: silent while typing"
    QTest.keyClick(_s, Qt.Key.Key_Return)
    QTest.keyClick(_s, Qt.Key.Key_Return)
    assert _got == ["abc"], f"Str_text: once on finish, not when unchanged - {_got}"

    # 단계 : 비면 None
    _s.selectAll()
    QTest.keyClick(_s, Qt.Key.Key_Delete)
    QTest.keyClick(_s, Qt.Key.Key_Return)
    assert _s.value() is None and _got[-1] is None, "Str_text: empty -> None"
    _s.set_value(None)
    assert _s.text() == "", "Str_text: None -> empty field"

    # 단계 : 목록 - 구분자로 가르고 빈 조각은 버림
    _l = List_text(None, separator=";")
    assert _l.value() is None, "List_text: empty -> None"
    _l.setText("a; ;b;")
    assert _l.value() == ["a", "b"], "List_text: drops empty pieces"
    _l.set_value(["x", "y"])
    assert _l.text() == "x; y", "List_text: joined by separator"

    # 실패 갈래 : 경로 갈래
    with pytest.raises(ValueError):
        Path_text(mode="save")

    # 단계 : 경로 - 시작 폴더는 기본값에서
    _dir = tmp_path / "d"
    _dir.mkdir()
    _file = _dir / "a.yaml"
    _file.write_text("")
    _p = Path_text(str(_file), mode="file")
    assert _p._start == str(_dir), "start dir: folder of a default file"

    # 단계 : 경로 - 고르면 시작 폴더가 따라감
    with mock.patch.object(QFileDialog, "getOpenFileName", return_value=("/etc/hosts", "")) as _dlg:
        _p._browse()
    assert _dlg.call_args.args[2] == str(_dir), "start dir: dialog opens at the last folder"
    assert _p._start == "/etc", "start dir: folder of the picked path"

    # 단계 : 경로 - 같은 글자면 안 냄
    _got: list = []
    _p.value_changed.connect(_got.append)
    _p._commit()
    assert _got == [], "path: silent when text unchanged"

    # 단계 : 디렉터리 갈래 - 비면 None, 디렉터리는 그 자리가 시작 폴더
    _d = Path_text(None, mode="dir")
    assert _d.value() is None, "dir: empty -> None"
    _d.set_value(str(_dir))
    assert _d._start == str(_dir), "start dir: a directory itself"

    # 단계 : 파일 여럿 - os.pathsep 으로 이음, 첫 경로가 시작 폴더
    _ps = Paths_text([str(_file), "/x/b.png"])
    assert _ps.value() == [str(_file), "/x/b.png"] and os.pathsep in _ps._edit.text(), "files: joined"
    assert _ps._start == str(_dir), "files: folder of the first path"
    _ps.set_value(None)
    assert _ps.value() is None, "files: None"
