"""설정 공간 - 파일 둘을 한 공간에 놓고, argv 로 공용 값을 덮어쓰고, 참조를 풀어 설정을 지음.

입력 `tests/resource/parser/`
- `hub.yaml` : `shared.patch`, `shared.name`, `run.tag`(`${shared.name}` 이 섞인 문자열)
- `model.yaml` : `config_type`, `patch`(`${shared.patch}` 하나), `depth`
- `broken.yaml` : 순환 참조 `a` <-> `b`, 없는 경로 참조 `lost`
- `nested.yaml` : 설정 필드 `backbone`(`${shared.patch}`), 설정 list `heads`(둘째는 `config_type: wide`), `spare: null`
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from python_toolbox.registry import Registry
from python_toolbox.run.parser import Config_Space
from python_toolbox.schema import Base_Config

_RES = Path(__file__).parent / "resource" / "parser"


@dataclass
class _Model_Config(Base_Config):
    patch: int = 0
    depth: int = 0
    kind: str = "base"


@dataclass
class _Conv_Config(_Model_Config):
    kernel: int = 3
    kind: str = "conv"


@dataclass
class _Run_Config(Base_Config):
    max_iters: int = 0
    tag: str = ""


@dataclass
class _Broken_Config(Base_Config):
    a: str = ""
    b: str = ""
    lost: str = ""


@dataclass
class _Head_Config(Base_Config):
    width: int = 0


@dataclass
class _Wide_Head_Config(_Head_Config):
    scale: int = 2


@dataclass
class _Net_Config(Base_Config):
    depth: int = 0
    backbone: _Head_Config = field(default_factory=_Head_Config)
    heads: list[_Head_Config] = field(default_factory=list)
    spare: _Head_Config | None = None


def test_config_space_flow():
    _space = Config_Space()

    # step : load two files into one space
    _space.Load(_RES / "hub.yaml")
    _space.Load(_RES / "model.yaml", at="model")
    assert _space.table["model.patch"] == "${shared.patch}", "load: reference kept as text"
    with pytest.raises(FileNotFoundError):
        _space.Load(_RES / "missing.yaml")

    # step : override a shared value from argv
    _space.Override(["shared.patch=64"])
    assert _space.table["shared.patch"] == 64, "override: yaml scalar to int"
    with pytest.raises(KeyError):
        _space.Override(["shared.ptch=1"])
    with pytest.raises(ValueError):
        _space.Override(["shared.patch"])

    # step : build - whole reference keeps type, mixed reference becomes text
    _model = _space.Build(_Model_Config, at="model")
    assert _model.patch == 64 and _model.depth == 50, "build: shared value through reference"
    _run = _space.Build(_Run_Config, at="run")
    assert _run.tag == "det_v1", "build: mixed reference to text"
    with pytest.raises(KeyError):
        _space.Build(_Model_Config, at="nowhere")
    with pytest.raises(TypeError):
        _space.Build(_Run_Config, at="model")

    # step : registry picks the subclass by config_type
    _registry = Registry[type[_Model_Config]]("model", _Model_Config)
    _registry.Register_module("conv")(_Conv_Config)
    _conv = _space.Build(_Model_Config, at="model", registry=_registry)
    assert type(_conv) is _Conv_Config and _conv.kernel == 3, "build: registry subclass"

    # step : schema defaults of the declared class do not hide the picked subclass's own defaults
    _layered = Config_Space()
    _layered.Load_schema(_Model_Config, at="model")
    _layered.Load(_RES / "hub.yaml")
    _layered.Load(_RES / "model.yaml", at="model")
    _picked = _layered.Build(_Model_Config, at="model", registry=_registry)
    assert type(_picked) is _Conv_Config and _picked.kind == "conv", "schema: subclass default kept"
    _layered.Override(["model.kind=custom"])
    assert _layered.Build(_Model_Config, at="model", registry=_registry).kind == "custom", "schema: override still wins"

    # step : nested config fields are built too - field, list, optional, registry inside
    _space.Load(_RES / "nested.yaml", at="net")
    _heads = Registry[type[_Head_Config]]("head", _Head_Config)
    _heads.Register_module("wide")(_Wide_Head_Config)
    _net = _space.Build(_Net_Config, at="net", registry=_heads)
    assert type(_net.backbone) is _Head_Config and _net.backbone.width == 64, "nested: field built"
    assert [type(_h) for _h in _net.heads] == [_Head_Config, _Wide_Head_Config], "nested: list built"
    assert _net.spare is None, "nested: optional none kept"
    _space.Override(["net.backbone=3"])
    with pytest.raises(TypeError):
        _space.Build(_Net_Config, at="net", registry=_heads)

    # step : broken references fail - cycle first, then the missing path once the cycle is cut
    _broken = Config_Space()
    _broken.Load(_RES / "broken.yaml")
    with pytest.raises(ValueError):
        _broken.Build(_Broken_Config)
    _broken.Override(["a=1", "b=2"])
    with pytest.raises(KeyError):
        _broken.Build(_Broken_Config)
