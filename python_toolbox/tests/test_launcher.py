"""Launcher - argv 나 설정 파일로 launcher 설정과 job 설정을 짓고, `jobs` key 마다 job 을 자기 프로세스로 띄우고, 결과를 받아 자기 기록에 남김.

입력 `tests/resource/launcher/`
- `hub.yaml` : `project_name`, `jobs.train`(`object_type: train`, `max_iters`), `jobs.broken`(`object_type: fail`), `shared.patch`
- `model.yaml` : `patch`(`${shared.patch}`), `depth` - `jobs.train.model` 아래에 놓임
- `nameless.yaml` : `project_name` 없음
job 클래스와 설정은 `tests/support/_jobs.py` - job 프로세스가 다시 import 함.

바탕 자리는 케이스마다 빈 폴더(`tmp_path`) - `BASE_ROOT` 를 바꿔 끼움.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from support._jobs import JOBS, Train_Config, Train_Job

from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.launcher import LAUNCHER_LOGGER, Launcher, Launcher_Config
from python_toolbox.run.log import LOG_DIR, Detach

_RES = Path(__file__).parent / "resource" / "launcher"


@dataclass
class _Det_Config(Launcher_Config):
    jobs: dict[str, Train_Config] = field(default_factory=dict)


class _Det_Launcher(Launcher):
    config: _Det_Config
    JOB_REGISTRY = JOBS


class _Jobless_Launcher(Launcher):
    config: _Det_Config


def test_launcher_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path))
    _hub = str(_RES / "hub.yaml")
    _model = f"{_RES / 'model.yaml'}@jobs.train.model"

    # step : build from argv - files, sub-config file at a path, override, job classes by object_type per key
    _launcher = _Det_Launcher.From_argv([_hub, _model, "shared.patch=64"])
    assert type(_launcher.config) is _Det_Config and list(_launcher.config.jobs) == ["train", "broken"], \
        "argv: declared config type, jobs by name"
    assert _launcher.config.jobs["train"].model.patch == 64, "argv: sub-config through shared override"
    assert _launcher.job_classes["train"] is Train_Job, "argv: job class called by object_type"
    assert _launcher.base_dir == tmp_path / "det" and (_launcher.base_dir / LOG_DIR).is_dir(), \
        "argv: base dir is the project name, log dir made at build"
    _coded = _Det_Launcher.From_files({"": _hub, "jobs.train.model": str(_RES / "model.yaml")}, ["shared.patch=64"])
    assert _coded.config == _launcher.config, "files: same build as argv"

    # step : bad argv or setup fails
    with pytest.raises(ValueError):
        _Det_Launcher.From_argv(["shared.patch=1"])
    with pytest.raises(ValueError):
        _Det_Launcher.From_argv([_hub, str(_RES / "model.yaml")])
    with pytest.raises(ValueError):
        _Det_Launcher.From_argv([str(_RES / "nameless.yaml")])
    with pytest.raises(ValueError):
        _Det_Launcher.From_argv([_hub, _model, "jobs.train.object_type="])
    with pytest.raises(TypeError):
        _Det_Launcher.From_argv([_hub, f"{_RES / 'model.yaml'}@jobs.train.modle"])
    with pytest.raises(KeyError):
        _Det_Launcher.From_argv([_hub, _model, "jobs.train.object_type=export"])
    with pytest.raises(TypeError):
        _Jobless_Launcher.From_argv([_hub, _model])

    # step : run - each job in its own process, results by name, job output in its own folder
    _results = _launcher.Run()
    assert _results["train"] == (0, _launcher.config.jobs["train"].Hash(), "Done"), "run: ok job -> (0, hash, Done)"
    assert _results["broken"][0] == 1, "run: failing job -> positive code"
    assert (_launcher.base_dir / "train" / "done.txt").read_text() == "64", "run: job wrote into its own folder"

    # step : launcher record - launched and ended per job, nothing else
    _events = [json.loads(_l) for _l in (_launcher.base_dir / LOG_DIR / "events.jsonl").read_text().splitlines()]
    assert {_e["name"] for _e in _events} == {LAUNCHER_LOGGER}, "record: launcher logger only"
    assert sorted((_e["message"], _e["job"]) for _e in _events) == \
        [("job ended", "broken"), ("job ended", "train"), ("job launched", "broken"), ("job launched", "train")], \
        "record: launched and ended per job"
    assert sorted(_p.name for _p in _launcher.base_dir.iterdir()) == [LOG_DIR, "train"], "record: no config left"

    # step : a job process that ends without a result is recorded by its exit code
    _crash = _Det_Launcher.From_argv([_hub, _model, "jobs.broken.object_type=crash"])
    _code, _, _content = _crash.Run()["broken"]
    assert _code == 3 and "without a result" in _content, "crash: exit code, no result"

    # step : a consumer moves the base dir by overriding Make_base_dir
    class _Elsewhere_Launcher(_Det_Launcher):
        def Make_base_dir(self) -> Path:
            _dir = tmp_path / "elsewhere" / self.config.project_name
            _dir.mkdir(parents=True, exist_ok=True)
            return _dir

    _moved = _Elsewhere_Launcher.From_argv([_hub, _model])
    assert _moved.Run()["train"][0] == 0, "override: job ran under the moved dir"
    assert (tmp_path / "elsewhere" / "det" / "train" / "done.txt").is_file(), "override: job got the moved dir"

    Detach(LAUNCHER_LOGGER)
