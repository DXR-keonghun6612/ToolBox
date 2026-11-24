"""torch job 설정 - GPU 없이 보는 흐름. launcher 설정 파일의 meta 로 학습 · export job 설정을 짓고, 정체성, run 폴더와 이어서 하기,
export 가 끝난 run 의 설정 읽기, 가중치 고르기, 지표 기록과 체크포인트 고르기.

입력 `tests/resource/launcher/`
- `launcher.yaml` : `project_name`, `meta.learning: file@./learning.yaml`
- `learning.yaml` : `config_type: supervised_Config`, `object_type: learning`, `max_iters`, `model: file@./model.yaml`,
  `mode.train`, `mode.val`(batch_size 는 `${learning.mode.train.loader.batch_size}`)
- `model.yaml` : `config_type: resnet_Config`, `variant`
- `export.yaml` : launcher 설정 파일 - `meta.export`(`config_type: export_job_Config`, `object_type: export`, 빈 `source`)

바탕 자리는 케이스마다 빈 폴더(`tmp_path`). 실제 학습, export 는 GPU 가 있는 곳에서 - `test_gpu_launcher.py`.
"""
from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest

from python_toolbox.registry import Registry
from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.job import Job
from python_toolbox.run.launcher import Launcher
from torch_toolbox.dataloader.definition import Dataloader_Config
from torch_toolbox.modules.model.backbone.resnet import ResNet_Config
from torch_toolbox.runner.config import Export_Job_Config
from torch_toolbox.runner.job import Export_Job
from torch_toolbox.runner.supervised.config import Supervised_Config
from torch_toolbox.runner.supervised.job import Supervised_Learning_Job
from torch_toolbox.runner.utils.log import log_iter
from torch_toolbox.runner.utils.weight import Iter_Selection, Max_of, Resolve_weight_path

_RES = Path(__file__).parent / "resource" / "launcher"
_JOBS = Registry[type[Job]]("torch_test_job", Job)


@_JOBS.Register_module("learning")
class _Learning(Supervised_Learning_Job):
    pass


@_JOBS.Register_module("export")
class _Export(Export_Job):
    Train_config = Supervised_Config


class _Launcher(Launcher):
    JOB_REGISTRY = _JOBS


def test_torch_job_config_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path / "base"))
    _file = str(_RES / "launcher.yaml")
    _export_file = str(_RES / "export.yaml")

    # step : build - job config picked by config_type from the meta, sub-configs by field, reference inside the job
    _space = _Launcher(_file).space
    _cfg = _space.Build("learning", Supervised_Config)
    assert type(_cfg) is Supervised_Config and _JOBS.Get(_cfg.object_type, Job) is _Learning, "build: learning job"
    assert type(_cfg.model) is ResNet_Config and _cfg.model.variant == "resnet18", "build: model file@ by config_type"
    assert type(_cfg.mode["train"].loader) is Dataloader_Config and _cfg.mode["val"].loader.batch_size == 4, \
        "build: mode loader config, reference followed"
    assert _cfg.gpus == [0], "build: default gpu"
    with pytest.raises(ValueError):
        _Launcher(_file, ["learning.gpus=[]"]).space.Build("learning", Supervised_Config)

    # step : export job config - its own config type, a finished run as source, options checked
    _ecfg = _Launcher(_export_file, ["export.source=/somewhere", "export.export.precision=FP16"]) \
        .space.Build("export", Export_Job_Config)
    assert type(_ecfg) is Export_Job_Config and _ecfg.export.precision == "FP16", "export: config and precision"
    assert _JOBS.Get(_ecfg.object_type, Job) is _Export, "export: job class"
    with pytest.raises(ValueError):
        _Launcher(_export_file).space.Build("export", Export_Job_Config)
    with pytest.raises(ValueError):
        _Launcher(_export_file, ["export.source=/x", "export.export.precision=FP64"]) \
            .space.Build("export", Export_Job_Config)

    # step : identity - run values do not move the hash, results-making values do
    _moved = dataclasses.replace(_cfg, max_iters=99, gpus=[1], test=True, start_iter=3, port_num=1)
    assert _moved.Hash() == _cfg.Hash(), "identity: run values out"
    assert dataclasses.replace(_cfg, use_amp=False).Hash() != _cfg.Hash(), "identity: training values in"

    # step : run dir - a new one under the base dir, resume passes with other run values, a lost one fails
    _dir = _Learning("learning", _cfg, tmp_path).Make_run_dir()
    assert _dir.is_dir() and _dir.parent == tmp_path, "run dir: new one under the base dir"
    _back = dataclasses.replace(_cfg, resume=str(_dir), max_iters=20)
    assert _Learning("learning", _back, tmp_path).Make_run_dir() == _dir, "resume: same run dir, more iterations"
    with pytest.raises(FileNotFoundError):
        _Learning("learning", dataclasses.replace(_cfg, resume=str(tmp_path / "nowhere")), tmp_path).Make_run_dir()

    # step : export reads the finished run's config - its own gpu and iteration, test mode
    _job = _Export("export", Export_Job_Config(source=str(_dir), gpu=0, start_iter=2), tmp_path)
    _train = _job._Read_train(_dir)
    assert type(_train) is Supervised_Config and type(_train.model) is ResNet_Config, "export: train config rebuilt"
    assert _train.model.variant == "resnet18" and _train.mode["train"].loader.batch_size == 4, "export: values kept"
    assert _train.gpus == [0] and _train.start_iter == 2 and _train.test is True, "export: its own run values"

    # step : weight path - resume picks from checkpoints by number, start_iter, given file, nothing
    _ckpt = _dir / "checkpoints"
    _ckpt.mkdir()
    for _i in (1, 2, 10):
        (_ckpt / f"checkpoint_{_i}.pt").touch()
    assert Resolve_weight_path(True, None, _dir, None) == str(_ckpt / "checkpoint_10.pt"), \
        "weight: last checkpoint by number"
    assert Resolve_weight_path(True, None, _dir, 2) == str(_ckpt / "checkpoint_2.pt"), "weight: start_iter"
    with pytest.raises(FileNotFoundError):
        Resolve_weight_path(True, None, _dir, 5)
    assert Resolve_weight_path(False, str(_ckpt / "checkpoint_1.pt"), _dir, None) is not None, "weight: given file"
    assert Resolve_weight_path(False, None, _dir, None) is None, "weight: nothing"

    # step : metric log written per iteration, selection reads it back
    _metric_log = logging.getLogger("job.learning.metric")
    log_iter(1, {"val": {"acc": {"accuracy": 0.5}}}, _dir, _metric_log)
    log_iter(2, {"val": {"acc": {"accuracy": 0.7}}}, _dir, _metric_log)
    assert (_dir / "avg" / "val" / "acc" / "iter_2.json").is_file(), "metric: json per iteration"
    assert Iter_Selection(Max_of, "val", "accuracy")(_dir) == 2, "metric: best iteration picked"
    assert Resolve_weight_path(True, None, _dir, None, Iter_Selection(Max_of, "val", "accuracy")) \
        == str(_ckpt / "checkpoint_2.pt"), "metric: selection drives the checkpoint"
