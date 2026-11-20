"""Runner - argv 로 파일 둘과 덮어쓰기를 받아 runner 설정과 하위 설정, job 을 짓고, Run 으로 결과 자리, 설정 파일, job 실행까지.

입력 `tests/resource/runner/`
- `hub.yaml` : `project_name`, `job: train`, `max_iters`, `shared.patch`
- `model.yaml` : `patch`(`${shared.patch}`), `depth` - `model` 아래에 놓임
- `nameless.yaml` : `project_name` 없음

결과 자리는 케이스마다 빈 폴더(`tmp_path`) - `RESULT_ROOT` 를 바꿔 끼움.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from python_toolbox.registry import Registry
from python_toolbox.run import runner as runner_module
from python_toolbox.run.job import Job
from python_toolbox.run.runner import Runner, Runner_Config
from python_toolbox.schema import Base_Config

_RES = Path(__file__).parent / "resource" / "runner"
_JOBS = Registry[type[Job]]("job", Job)


@dataclass
class _Model_Config(Base_Config):
    patch: int = 0
    depth: int = 0


@dataclass
class _Train_Config(Runner_Config):
    max_iters: int = 0
    model: _Model_Config = field(default_factory=_Model_Config)


@_JOBS.Register_module("train")
class _Train_Job(Job):
    def Work(self) -> None:
        (self.result_dir / "done.txt").write_text(str(self.config.model.patch))


class _Train_Runner(Runner):
    config: _Train_Config
    JOB_REGISTRY = _JOBS


class _Jobless_Runner(Runner):
    config: _Train_Config


class _Longer_Runner(_Train_Runner):
    RESUME_FREE = frozenset({"max_iters"})


def test_runner_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "RESULT_ROOT", str(tmp_path))
    _hub = str(_RES / "hub.yaml")
    _model = f"{_RES / 'model.yaml'}@model"

    # step : build from argv - files, sub-config file at a path, override, job from registry
    _runner = _Train_Runner.From_argv([_hub, _model, "shared.patch=64"])
    assert type(_runner.config) is _Train_Config, "argv: declared config type"
    assert _runner.config.model.patch == 64, "argv: sub-config through shared override"
    assert _runner.result_dir.parent == tmp_path / "det", "argv: result dir under project name"
    assert type(_runner.job) is _Train_Job, "argv: job picked by config.job"

    # step : bad argv or setup fails
    with pytest.raises(ValueError):
        _Train_Runner.From_argv(["shared.patch=1"])
    with pytest.raises(ValueError):
        _Train_Runner.From_argv([_hub, str(_RES / "model.yaml")])
    with pytest.raises(ValueError):
        _Train_Runner.From_argv([str(_RES / "nameless.yaml")])
    with pytest.raises(ValueError):
        _Train_Runner.From_argv([_hub, _model, "job="])
    with pytest.raises(TypeError):
        _Train_Runner.From_argv([_hub, f"{_RES / 'model.yaml'}@modle"])
    with pytest.raises(KeyError):
        _Train_Runner.From_argv([_hub, _model, "job=export"])
    with pytest.raises(TypeError):
        _Jobless_Runner.From_argv([_hub, _model])

    # step : result dir is made once
    assert _runner.Make_result_dir() is True, "result dir: made first time"
    assert _runner.Make_result_dir() is False, "result dir: second call does nothing"

    # step : run - config file left, job runs with config and result dir
    assert _runner.Run() is True, "run: job finished without error records"
    assert (_runner.result_dir / "done.txt").read_text() == "64", "run: job wrote into result dir"
    assert (_runner.result_dir / "run.log").is_file(), "run: default log file in result dir"
    assert (_runner.result_dir / "events.jsonl").is_file(), "run: default event file in result dir"

    # step : the saved config alone rebuilds the same config
    _again = _Train_Runner.From_argv([str(_runner.config_path)])
    assert _again.config == _runner.config, "rebuild: same config from saved file"

    # step : resume - same run dir, only free paths may differ
    _resume = f"resume={_runner.result_dir}"
    _back = _Train_Runner.From_argv([_hub, _model, "shared.patch=64", _resume, "job=train", "log.root.level=DEBUG"])
    assert _back.result_dir == _runner.result_dir, "resume: same run dir"
    assert _back.config.log["root"].level == "DEBUG", "resume: log may differ, built as Log_Config"
    with pytest.raises(ValueError):
        _Train_Runner.From_argv([_hub, _model, "shared.patch=16", _resume])
    with pytest.raises(ValueError):
        _Train_Runner.From_argv([_hub, _model, "shared.patch=64", "max_iters=200", _resume])
    _longer = _Longer_Runner.From_argv([_hub, _model, "shared.patch=64", "max_iters=200", _resume])
    assert _longer.config.max_iters == 200, "resume: whitelisted path may differ"
    with pytest.raises(FileNotFoundError):
        _Train_Runner.From_argv([_hub, _model, f"resume={tmp_path / 'nowhere'}"])
