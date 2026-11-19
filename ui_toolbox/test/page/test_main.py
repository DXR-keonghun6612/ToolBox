"""main 골격 - config 를 central widget 에, root 묶음과 find, 공통 style, 닫힐 때 멈춤, yaml 경로, app.Run.

입력 `test/resource/page/main.yaml` : root node - `title`, `class: qt_QVBoxLayout`, `link: {pick}`(detail.yaml 의 영역),
`items: {body: {items: detail.yaml}}`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from ui_toolbox.app import Run
from ui_toolbox.page import Main

_RESOURCE = Path(__file__).parents[1] / "resource" / "page"

_CONFIG = {"title": "Main", "class": "qt_QVBoxLayout",
           "items": {"body": {"class": "qt_QVBoxLayout", "items": {"note": {"class": "qt_QLabel", "args": {"text": "n"}}}}},
           "style": {"note": {"color": "red"}}}


def test_main_flow():
    # 단계 : 짓기 - central widget 에 채움, 창 제목
    _m = Main(_CONFIG)
    assert _m.windowTitle() == "Main", "build: window title"
    assert _m.centralWidget().items is _m.items, "build: root names lifted"

    # 단계 : find - items.find 로
    assert isinstance(_m.find("body.note"), QLabel), "find: path"
    with pytest.raises(KeyError):
        _m.find("body.nothing")

    # 단계 : style - 공통 style 아래에 root style
    _sheet = _m.centralWidget().styleSheet()
    assert "Readout" in _sheet and "#note { color: red; }" in _sheet, "style: base under root style"
    assert "#ff0000" in Main(_CONFIG, tokens={"muted": "#ff0000"}).centralWidget().styleSheet(), "style: tokens"

    # 단계 : 닫힐 때 - 넣은 차례로 부름
    _got: list = []
    _m.on_close(lambda: _got.append("a"))
    _m.on_close(lambda: _got.append("b"))
    _m.close()
    assert _got == ["a", "b"], "close: stops in order"

    # 단계 : yaml 경로 - 그 폴더가 base
    _f = Main(_RESOURCE / "main.yaml")
    assert _f.windowTitle() == "From file" and _f.find("body.note").text() == "detail", "file: base is its folder"

    # 실패 갈래 : 없는 파일
    with pytest.raises(ValueError):
        Main(_RESOURCE / "nothing.yaml")


def test_run_flow():
    # 단계 : 같은 토큰이 콜러블로, 루프가 끝나면 종료 코드
    _seen: list = []

    def _build(tokens):
        _seen.append(tokens["accent"])
        QTimer.singleShot(0, QApplication.quit)          # 루프가 서면 바로 끝냄
        return Main(_CONFIG, tokens=tokens)

    assert Run(_build, tokens={"accent": "#123456"}) == 0, "run: exit code"
    assert _seen == ["#123456"], "run: tokens passed to build"
