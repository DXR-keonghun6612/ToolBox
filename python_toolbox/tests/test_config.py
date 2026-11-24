"""설정 공간 - root 파일을 겹치고 `file@`, `config@` 를 펼쳐 meta 를 만들고, argv 로 덮고, 참조를 풀어 고른 설정 하나를 지음.

입력 `tests/resource/config/`
- `hub.yaml` : `data`(`${model.patch}` 하나, 참조 list, 섞인 글 `tag`), `model: file@./model.yaml`, `net: file@./net/net.yaml`
- `model.yaml` : `config_type: test_conv_Config`, `patch`, `depth`
- `res.yaml` : `config_type: test_res_Config`, `depth` - argv `file@` 로 `model` 을 바꿈
- `net/net.yaml` : `backbone`(`${model.patch}`), `heads`(`config@`, `null` 원소), `bag.one: file@./head.yaml` - 그 파일 폴더 기준
- `net/head.yaml` : `width`
- `extra.yaml` : 둘째 root 파일 - `data.name` 만
- `loop.yaml` : 자기 자신을 `file@`
- `broken.yaml` : 순환 참조 `a` <-> `b`, 없는 경로 참조 `lost`
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from python_toolbox.config import CONFIGS, Base_Config, Config_Space

_RES = Path(__file__).parent / "resource" / "config"


@dataclass
class _Model_Config(Base_Config):
    patch: int = 0
    depth: int = 0
    lr: float = 0.1
    kind: str = "base"


@CONFIGS.Register_module("test_conv_Config")
@dataclass
class _Conv_Config(_Model_Config):
    kernel: int = 3
    kind: str = "conv"


@CONFIGS.Register_module("test_res_Config")
@dataclass
class _Res_Config(_Model_Config):
    kind: str = "res"


@dataclass
class _Head_Config(Base_Config):
    width: int = 0


@CONFIGS.Register_module("test_wide_head_Config")
@dataclass
class _Wide_Head_Config(_Head_Config):
    scale: int = 2


@CONFIGS.Register_module("test_net_Config")
@dataclass
class _Net_Config(Base_Config):
    backbone: _Head_Config = field(default_factory=_Head_Config)
    heads: list[_Head_Config] = field(default_factory=list)
    bag: dict[str, _Head_Config] = field(default_factory=dict)
    spare: _Head_Config | None = None


@CONFIGS.Register_module("test_data_Config")
@dataclass
class _Data_Config(Base_Config):
    name: str = ""
    patch: int = 0
    sizes: list[int | None] = field(default_factory=list)
    tag: str = ""


def test_config_space_flow(monkeypatch):
    _space = Config_Space()

    # step : load - file@ placed and nested by its own folder, config@ expanded, references read through
    _space.Load(_RES / "hub.yaml")
    assert _space.Get("model.patch") == 32, "load: file@ content in place"
    assert _space.Get("net.bag.one.width") == 4, "load: nested file@ relative to its file"
    assert _space.Get("net.heads")[1:] == [{"config_type": "test_wide_head_Config"}, None], \
        "load: config@ expanded, None element kept"
    assert _space.Get("data.sizes") == [32, 50, None], "load: whole references in a list keep type"
    assert _space.Get("data.tag") == "det_v1", "load: mixed reference to text"
    with pytest.raises(FileNotFoundError):
        _space.Load(_RES / "missing.yaml")
    with pytest.raises(ValueError):
        _space.Load(_RES / "loop.yaml")

    # step : second root file overlays - dict merged inside, other keys kept
    _space.Load(_RES / "extra.yaml")
    assert _space.Get("data.name") == "cls" and _space.Get("data.patch") == 32, "overlay: merged inside"

    # step : override - value replaced, field not in the file added, references follow
    _space.Override(["model.patch=64", "model.kernel=5", "model.lr=1"])
    assert _space.Get("data.patch") == 64 and _space.Get("model.kernel") == 5, "override: replaced, added"
    with pytest.raises(ValueError):
        _space.Override(["model.patch"])
    with pytest.raises(ValueError):
        _space.Override(["model.patch.x=1"])
    with pytest.raises(KeyError):
        _space.Override(["model=config@nowhere"])

    # step : build - one picked config, subclass by config_type, defaults for unwritten fields
    _model = _space.Build("model", _Model_Config)
    assert type(_model) is _Conv_Config and (_model.patch, _model.kernel, _model.lr, _model.kind) == (64, 5, 1, "conv"), \
        "build: subclass, overrides, int into float, default"
    assert _space.Build("data", _Data_Config).sizes == [64, 50, None], "build: list field as is"
    _net = _space.Build("net", _Net_Config)
    assert type(_net.backbone) is _Head_Config and _net.backbone.width == 64, "build: nested field by annotation"
    assert [type(_h) for _h in _net.heads[:2]] == [_Head_Config, _Wide_Head_Config] and _net.heads[2] is None, \
        "build: list of configs, picked inside, None element kept"
    assert _net.bag["one"].width == 4 and _net.spare is None, "build: dict of configs, optional None"
    _space.Override(["net.bag.two.width=3"])
    assert _space.Build("net", _Net_Config).bag["two"].width == 3, "build: new dict key from argv"
    with pytest.raises(TypeError):
        _space.Build("model", _Head_Config)
    with pytest.raises(ValueError):
        _space.Build("net.backbone", _Head_Config)

    # step : build from a dict alone - no file
    _alone = Config_Space({"m": {"config_type": "test_conv_Config", "depth": True}}).Build("m", _Model_Config)
    assert _alone.depth is True, "dict: built without a file, bool into int"

    # step : field checks at construction - type, None, unknown field, unregistered, not a mapping
    for _bad, _error in [
        ({"depth": "abc"}, TypeError),
        ({"depth": None}, TypeError),
        ({"knl": 1}, TypeError),
        ({"config_type": "nowhere"}, KeyError),
    ]:
        with pytest.raises(_error):
            Config_Space({"m": {"config_type": "test_conv_Config", **_bad}}).Build("m", _Model_Config)
    with pytest.raises(TypeError):
        Config_Space({"n": {"config_type": "test_net_Config", "backbone": None}}).Build("n", _Net_Config)
    with pytest.raises(TypeError):
        Config_Space({"n": {"config_type": "test_net_Config", "backbone": 3}}).Build("n", _Net_Config)

    # step : replace - file@, config@ over a dict replace it, references to dropped values fail
    monkeypatch.chdir(_RES)
    _space.Override(["model=file@./res.yaml"])
    assert _space.Get("model") == {"config_type": "test_res_Config", "depth": 101}, "replace: file@ from cwd"
    assert type(_space.Build("model", _Model_Config)) is _Res_Config, "replace: other subclass"
    _space.Override(["model=config@test_conv_Config"])
    assert _space.Get("model") == {"config_type": "test_conv_Config"}, "replace: config@"
    with pytest.raises(KeyError):
        _space.Build("data", _Data_Config)

    # step : broken references fail - cycle, missing path
    _broken = Config_Space()
    _broken.Load(_RES / "broken.yaml")
    with pytest.raises(ValueError):
        _broken.Get("a")
    with pytest.raises(KeyError):
        _broken.Get("lost")
