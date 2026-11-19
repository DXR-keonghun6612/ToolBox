"""component - 기능 단위 등록표. 키는 클래스 이름.

여기서 component 를 전부 불러 표를 만듦 - 목록이 한 곳에 보이고, import 부수 효과에 안 기댐.
UI 객체로 쓰는 것만 올림 - 골격(`Editor_base`), 도구, 층, model 은 안 올림.
표는 python_toolbox `Registry` - `QWidget` 하위 클래스만. 소비처가 만든 component 도 `register` 로 올림.
검사는 등록 시점 - 이름이 겹치면 실패. 없는 이름을 찾으면(`REGISTRY.Get`) 실패, 기본으로 안 물러남.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from python_toolbox.registry import Registry

from .control._bool import Bool_check, Bool_toggle
from .control._choice import Choice_combo, Choice_radio, Choices_check
from .control._number import Float_slider, Float_spin, Int_slider, Int_spin
from .control._readout import Readout
from .control._text import List_text, Path_text, Paths_text, Str_text
from .editor.raster._editor import Raster_editor
from .layout._fold import Fold
from .progress._bar import Progress_bar
from .table._view import Table_view
from .tree._view import Tree_view

__all__ = ["REGISTRY", "register"]

#: 등록표 - 클래스 이름 -> 클래스.
REGISTRY: Registry[type[QWidget]] = Registry("component", QWidget)


def register(cls: type) -> type:
    """component 클래스를 클래스 이름 그대로 올림. 데코레이터로도 씀.

    `REGISTRY.Register_module()` 을 이름 없이 부르면 key 가 소문자 - config 가 못 찾음.

    Raises:
        TypeError: `QWidget` 하위 클래스가 아닐 때.
        KeyError: 이미 있는 이름일 때.
    """
    return REGISTRY.Register_module(getattr(cls, "__name__", None))(cls)


for _cls in (Bool_check, Bool_toggle,
             Int_spin, Float_spin, Int_slider, Float_slider,
             Str_text, List_text, Path_text, Paths_text,
             Choice_combo, Choice_radio, Choices_check,
             Readout,
             Table_view, Tree_view, Progress_bar, Raster_editor,
             Fold):
    register(_cls)
