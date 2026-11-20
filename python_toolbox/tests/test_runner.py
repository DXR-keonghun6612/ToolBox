"""Runner - argv 로 파일 둘과 덮어쓰기를 받아 runner 설정과 하위 설정, job 을 짓고, 결과 자리와 기록 폴더를 세우고, Run 으로 job 실행까지.

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
from python_toolbox.run.runner import LOG_DIR, Runner, Runner_Config
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
        _dir = self.result_dir / "train"
        _dir.mkdir(exist_ok=True)
        (_dir / "done.txt").write_text(str(self.config.model.patch))


class _Train_Runner(Runner):
    config: _Train_Config
    JOB_REGISTRY = _JOBS


class _Jobless_Runner(Runner):
    config: _Train_Config


def test_runner_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "RESULT_ROOT", str(tmp_path))
    _hub = str(_RES / "hub.yaml")
    _model = f"{_RES / 'model.yaml'}@model"

    # step : build from argv - files, sub-config file at a path, override, job from registry, result dir and log dir made
    _runner = _Train_Runner.From_argv([_hub, _model, "shared.patch=64"])
    assert type(_runner.config) is _Train_Config, "argv: declared config type"
    assert _runner.config.model.patch == 64, "argv: sub-config through shared override"
    assert _runner.result_dir == tmp_path / "det", "argv: result dir is the project name"
    assert (_runner.result_dir / LOG_DIR).is_dir(), "argv: log dir made at build"
    assert type(_runner.job) is _Train_Job, "argv: job picked by config.job"
    assert _runner.job.result_dir == _runner.result_dir, "argv: job got the result dir"

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

    # step : run - job writes into its own folder, records go to the log dir, no config file left
    assert _runner.Run() is True, "run: job finished without error records"
    assert (_runner.result_dir / "train" / "done.txt").read_text() == "64", "run: job wrote into its own folder"
    assert (_runner.result_dir / LOG_DIR / "run.log").is_file(), "run: default log file in log dir"
    assert (_runner.result_dir / LOG_DIR / "events.jsonl").is_file(), "run: default event file in log dir"
    assert sorted(_p.name for _p in _runner.result_dir.iterdir()) == [LOG_DIR, "train"], "run: runner left nothing else"

    # step : another run - same result dir, no folder per run
    _again = _Train_Runner.From_argv([_hub, _model, "shared.patch=16"])
    assert _again.result_dir == _runner.result_dir, "again: same result dir"
    assert _again.Run() is True, "again: job finished"
    assert (_runner.result_dir / "train" / "done.txt").read_text() == "16", "again: job folder reused"

    # step : a consumer moves the result dir by overriding Make_result_dir
    class _Elsewhere_Runner(_Train_Runner):
        def Make_result_dir(self) -> Path:
            _dir = tmp_path / "elsewhere" / self.config.project_name
            _dir.mkdir(parents=True, exist_ok=True)
            return _dir

    _moved = _Elsewhere_Runner.From_argv([_hub, _model])
    assert _moved.result_dir == tmp_path / "elsewhere" / "det", "override: result dir from the consumer"
    assert _moved.job.result_dir == _moved.result_dir, "override: job got the moved dir"
    assert _moved.Run() is True, "override: job finished"
    assert (_moved.result_dir / LOG_DIR / "run.log").is_file(), "override: log dir under the moved dir"
