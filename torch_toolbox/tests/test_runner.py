"""torch runner - GPU 없이 보는 흐름. argv 로 지도학습 설정과 job 을 짓고, export 옵션, 이어서 하기 확인, 가중치 고르기, 지표 기록과 체크포인트 고르기.

입력 `tests/resource/runner/`
- `hub.yaml` : `project_name`, `job: learning`, `max_iters`, `shared.depth`, `mode.train`(loader, batch_monitoring)
- `model.yaml` : `config_type: resnet_Config`, `variant: resnet${shared.depth}` - `model` 아래에 놓임

결과 자리는 케이스마다 빈 폴더(`tmp_path`) - `RESULT_ROOT` 를 바꿔 끼움. 실제 학습, export 는 GPU 가 있는 곳에서 사용처가 돌림.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from python_toolbox.file import Write_to
from python_toolbox.registry import Registry
from python_toolbox.run import runner as runner_module
from python_toolbox.run.job import Job
from torch_toolbox.dataloader.definition import Dataloader_Config
from torch_toolbox.modules.model.backbone.resnet import ResNet_Config
from torch_toolbox.runner.job import Export_Job
from torch_toolbox.runner.runner import Torch_Runner
from torch_toolbox.runner.supervised.config import Supervised_Config
from torch_toolbox.runner.supervised.job import Supervised_Learning_Job
from torch_toolbox.runner.utils.log import log_iter
from torch_toolbox.runner.utils.weight import Iter_Selection, Max_of, Resolve_weight_path

_RES = Path(__file__).parent / "resource" / "runner"
_JOBS = Registry[type[Job]]("torch_test_job", Job)


@_JOBS.Register_module("learning")
class _Learning(Supervised_Learning_Job):
    pass


@_JOBS.Register_module("export")
class _Export(Export_Job):
    pass


class _Runner(Torch_Runner):
    config: Supervised_Config
    JOB_REGISTRY = _JOBS


def test_torch_runner_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "RESULT_ROOT", str(tmp_path))
    _base = [str(_RES / "hub.yaml"), f"{_RES / 'model.yaml'}@model"]

    # step : build - sub-configs from the registry, shared value through reference, job by name
    _runner = _Runner.From_argv(_base)
    assert type(_runner.config.model) is ResNet_Config and _runner.config.model.variant == "resnet18", \
        "build: model config picked by config_type, variant through shared"
    _train = _runner.config.mode["train"]
    assert type(_train.loader) is Dataloader_Config and _train.loader.batch_size == 4, "build: mode loader config"
    assert type(_runner.job) is _Learning and _runner.config.gpus == [0], "build: learning job, default gpu"

    # step : export options and bad values
    _export = _Runner.From_argv([*_base, "job=export", "export.precision=FP16"])
    assert type(_export.job) is _Export and _export.config.export.precision == "FP16", "export: job and precision"
    with pytest.raises(ValueError):
        _Runner.From_argv([*_base, "export.precision=FP64"])
    with pytest.raises(ValueError):
        _Runner.From_argv([*_base, "gpus=[]"])

    # step : resume - device, iterations, job, export may differ, the model may not
    _runner.Make_result_dir()
    Write_to(_runner.config_path, _runner.config.Serialize())
    _resume = f"resume={_runner.result_dir}"
    _back = _Runner.From_argv([*_base, _resume, "job=export", "max_iters=20", "gpus=[1]", "test=true"])
    assert _back.result_dir == _runner.result_dir, "resume: same run dir"
    with pytest.raises(ValueError):
        _Runner.From_argv([*_base, _resume, "shared.depth=50"])

    # step : weight path - resume picks from checkpoints by number, start_iter, given file, nothing
    _ckpt = _runner.result_dir / "checkpoints"
    _ckpt.mkdir()
    for _i in (1, 2, 10):
        (_ckpt / f"checkpoint_{_i}.pt").touch()
    assert Resolve_weight_path(True, None, _runner.result_dir, None) == str(_ckpt / "checkpoint_10.pt"), \
        "weight: last checkpoint by number"
    assert Resolve_weight_path(True, None, _runner.result_dir, 2) == str(_ckpt / "checkpoint_2.pt"), "weight: start_iter"
    with pytest.raises(FileNotFoundError):
        Resolve_weight_path(True, None, _runner.result_dir, 5)
    assert Resolve_weight_path(False, str(_ckpt / "checkpoint_1.pt"), _runner.result_dir, None) is not None, \
        "weight: given file"
    assert Resolve_weight_path(False, None, _runner.result_dir, None) is None, "weight: nothing"

    # step : metric log written per iteration, selection reads it back
    log_iter(1, {"val": {"acc": {"accuracy": 0.5}}}, _runner.result_dir)
    log_iter(2, {"val": {"acc": {"accuracy": 0.7}}}, _runner.result_dir)
    assert (_runner.result_dir / "avg" / "val" / "acc" / "iter_2.json").is_file(), "metric: json per iteration"
    assert Iter_Selection(Max_of, "val", "accuracy")(_runner.result_dir) == 2, "metric: best iteration picked"
    assert Resolve_weight_path(True, None, _runner.result_dir, None, Iter_Selection(Max_of, "val", "accuracy")) \
        == str(_ckpt / "checkpoint_2.pt"), "metric: selection drives the checkpoint"
