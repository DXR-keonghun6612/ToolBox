"""Launcher - launcher 설정 파일로 자기 설정과 meta 를 만들고, `Run` 때 meta 의 job 마다 설정을 지어 자기 프로세스로 띄우고, 결과를 자기 기록에 남김.

입력 `tests/resource/launcher/`
- `launcher.yaml` : `project_name`, `log`(`DEBUG`, JSON 출력 `events.jsonl` 하나), `meta.train`(`file@./train.yaml`), `meta.broken`(`object_type: fail`)
- `train.yaml` : `config_type: test_train_job`, `object_type: train`, `max_iters`, `model: file@./model.yaml`
- `model.yaml` : `patch`, `depth`
- `big.yaml` : 다른 `patch` - argv `file@` 로 `train.model` 을 바꿈
job 클래스와 설정은 `tests/support/_jobs.py` - job 프로세스가 다시 import 함.

바탕 자리는 케이스마다 빈 폴더(`tmp_path`) - `BASE_ROOT` 를 바꿔 끼움.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from support._jobs import JOBS, Train_Config

from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.launcher import LAUNCHER_LOGGER, Launcher, Launcher_Config
from python_toolbox.run.log import LOG_DIR, Detach

_RES = Path(__file__).parent / "resource" / "launcher"


@dataclass
class _Det_Config(Launcher_Config):
    note: str = ""


class _Det_Launcher(Launcher):
    config: _Det_Config
    JOB_REGISTRY = JOBS


class _Jobless_Launcher(Launcher):
    config: _Det_Config


def _Events(base_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (base_dir / LOG_DIR / "events.jsonl").read_text().splitlines()]


def test_launcher_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path))
    _file = str(_RES / "launcher.yaml")

    # step : build from argv - own config by the declared class, meta from its file, overrides on meta
    _launcher = _Det_Launcher.From_argv([_file, "train.model.patch=64"])
    assert type(_launcher.config) is _Det_Config and _launcher.config.log.level == "DEBUG", \
        "argv: declared config class, nested config built"
    assert type(_launcher.config.log.output[0]).__name__ == "Log_Output", "argv: list of configs built"
    assert _launcher.space.Get("train.max_iters") == 100, "argv: meta file@ relative to the launcher file"
    assert _launcher.space.Get("train.model.patch") == 64, "argv: override on meta"
    assert _launcher.base_dir == tmp_path / "det" and (_launcher.base_dir / LOG_DIR).is_dir(), \
        "argv: base dir is the project name, log dir made at build"
    with pytest.raises(ValueError):
        _Det_Launcher.From_argv([])
    with pytest.raises(ValueError):
        _Det_Launcher.From_argv([_file, "train.max_iters"])
    with pytest.raises(FileNotFoundError):
        _Det_Launcher.From_argv([str(_RES / "missing.yaml")])
    with pytest.raises(TypeError):
        _Jobless_Launcher.From_argv([_file])

    # step : run - each job in its own process, results by name, job output in its own folder
    _results = _launcher.Run()
    _train = _launcher.space.Build("train", Train_Config)
    assert _results["train"] == (0, _train.Hash(), "Done"), "run: ok job -> (0, hash, Done)"
    assert _results["broken"][0] == 1, "run: failing job -> positive code"
    assert (_launcher.base_dir / "train" / "done.txt").read_text() == "64", "run: job wrote into its own folder"

    # step : launcher record - launched and ended per job, nothing else
    _events = _Events(_launcher.base_dir)
    assert {_e["name"] for _e in _events} == {LAUNCHER_LOGGER}, "record: launcher logger only"
    assert sorted((_e["message"], _e["job"]) for _e in _events) == \
        [("job ended", "broken"), ("job ended", "train"), ("job launched", "broken"), ("job launched", "train")], \
        "record: launched and ended per job"
    assert sorted(_p.name for _p in _launcher.base_dir.iterdir()) == [LOG_DIR, "train"], "record: no config left"

    # step : a meta change after build reaches the next run
    _launcher.space.Override(["train.model.patch=7"])
    assert _launcher.Run()["train"][0] == 0 and (_launcher.base_dir / "train" / "done.txt").read_text() == "7", \
        "change: built at run"

    # step : a broken job config stops the run before any launch
    _count = len(_Events(_launcher.base_dir))
    for _bad, _error in [("train.max_iter=1", TypeError), ("broken.object_type=export", KeyError),
                         ("broken.config_type=", ValueError)]:
        _bad_launcher = _Det_Launcher.From_argv([_file, _bad])
        with pytest.raises(_error):
            _bad_launcher.Run()
    assert len(_Events(_launcher.base_dir)) == _count, "broken: nothing launched, nothing recorded"

    # step : a job process that ends without a result is recorded by its exit code
    _crash = _Det_Launcher.From_argv([_file, "broken.object_type=crash"])
    _code, _, _content = _crash.Run()["broken"]
    assert _code == 3 and "without a result" in _content, "crash: exit code, no result"

    # step : a consumer moves the base dir; argv file@ swaps a job part relative to cwd
    class _Elsewhere_Launcher(_Det_Launcher):
        def Make_base_dir(self) -> Path:
            _dir = tmp_path / "elsewhere" / self.config.project_name
            _dir.mkdir(parents=True, exist_ok=True)
            return _dir

    monkeypatch.chdir(_RES)
    _moved = _Elsewhere_Launcher.From_argv([_file, "train.model=file@./big.yaml"])
    assert _moved.Run()["train"][0] == 0, "override: job ran under the moved dir"
    assert (tmp_path / "elsewhere" / "det" / "train" / "done.txt").read_text() == "128", \
        "override: job got the moved dir and the swapped file"

    Detach(LAUNCHER_LOGGER)
