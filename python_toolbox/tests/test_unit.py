"""실행 단위 설정 - 정체성은 노드마다 자기 root 의 빼는 칸만 빼고, `config_type` · `object_type` 은 넣고, hash 는 정체성이 같으면 같고, Diff 는 다른 경로를 냄.

입력 파일 없음. 설정은 test 안의 선언.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from python_toolbox.config import Base_Config
from python_toolbox.run.job import Job_Config
from python_toolbox.run.log import Log_Config
from python_toolbox.run.unit import Diff, Unit_Config
from python_toolbox.schema import Walk, Walk_rule


@dataclass
class _Head(Base_Config):
    width: int = 8


@dataclass
class _Model(Unit_Config):
    depth: int = 18
    head: _Head = field(default_factory=_Head)


@dataclass
class _Train(Job_Config):
    epochs: int = 1
    workers: int = 1
    model: _Model = field(default_factory=_Model)

    __exclude_identity__: ClassVar[set[str]] = {"workers"}


def test_unit_flow():
    _base = _Train(object_type="train", model=_Model(object_type="resnet"))

    # step : identity - each node drops only its own excluded fields, type fields stay
    _id = _base.Identity()
    assert {"log", "resume", "workers"}.isdisjoint(_id), "identity: frame and declared run values out at job root"
    assert _id["object_type"] == "train" and "config_type" in _id, "identity: type fields kept"
    assert "log" not in _id["model"] and _id["model"]["object_type"] == "resnet", "identity: nested unit by its own rule"
    assert _id["model"]["head"] == {"config_type": "", "object_type": "", "width": 8}, "identity: plain config whole"

    # step : hash - same identity same hash, run values and logs do not move it, results-making values do
    _same = _Train(object_type="train", model=_Model(object_type="resnet"), workers=8, resume="somewhere",
                   log=Log_Config(level="DEBUG"))
    assert _same.Hash() == _base.Hash(), "hash: excluded fields ignored"
    assert _Train(object_type="train", model=_Model(object_type="convnext")).Hash() != _base.Hash(), \
        "hash: nested object_type counts"
    assert _Train(object_type="train", epochs=2, model=_Model(object_type="resnet")).Hash() != _base.Hash(), \
        "hash: own field counts"

    # step : diff against a saved config (field names, as a job leaves it) - only saved keys, excluded ones skipped
    _saved = Walk(_base, Walk_rule())
    assert Diff(_saved, _same) == [], "diff: excluded fields differ, nothing reported"
    _saved["model"]["depth"] = 50
    _saved["model"]["head"]["width"] = 4
    _saved["gone"] = 1
    assert Diff(_saved, _base) == ["gone", "model.depth", "model.head.width"], "diff: every differing path"
    del _saved["epochs"]
    assert "epochs" not in Diff(_saved, _base), "diff: a field missing from the saved config is not compared"
