"""torch runner - GPU 한 장에서 실제로 도는 흐름. 학습 -> 이어서 학습 -> 고른 체크포인트로 test -> ONNX export, 이른 멈춤, 실패 기록.

입력 `tests/resource/gpu/`
- `hub.yaml` : `project_name: toy`, `job: learning`, `max_iters: 3`, `shared.classes`, `mode` 의 train / val / test(합성 데이터셋, scalar 지표)
- `model.yaml` : `toy_model_Config`(in_dim 4, classes `${shared.classes}`) - `model` 아래
- `loss.yaml` : `logits` 에 cross entropy - `loss` 아래
- `optim.yaml` : SGD - `optim` 아래

합성 데이터셋, 모델은 이 파일이 등록. 결과 자리는 케이스마다 빈 폴더(`tmp_path`). GPU 가 없으면 건너뜀. DDP(GPU 둘 이상)는 안 봄.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime
import pytest
import torch
import torch.nn as nn

import torch_toolbox.metric.component.scalar  # noqa: F401 - scalar_accumulator 등록
from python_toolbox.registry import Registry
from python_toolbox.run import runner as runner_module
from python_toolbox.run.job import Job
from python_toolbox.run.log import CONSOLE, Log_Config, Setup_log
from torch_toolbox import CFGS, Mode
from torch_toolbox.dataloader import DATASETS
from torch_toolbox.dataloader.definition import Custom_Dataset, Dataset_Config
from torch_toolbox.modules import MODELS
from torch_toolbox.modules.model.definition import Trainable_Model, Trainable_Model_Config
from torch_toolbox.runner.config import Export_Config
from torch_toolbox.runner.job import Export_Job
from torch_toolbox.runner.runner import Torch_Runner
from torch_toolbox.runner.supervised.assembler import Supervised_Assembler
from torch_toolbox.runner.supervised.config import Supervised_Config
from torch_toolbox.runner.supervised.job import Supervised_Learning_Job
from torch_toolbox.runner.utils.weight import Iter_Selection, Max_of

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")

_RES = Path(__file__).parent / "resource" / "gpu"
_JOBS = Registry[type[Job]]("torch_gpu_test_job", Job)
_BEST = Iter_Selection(Max_of, "val", "accuracy")


# ── 합성 데이터셋, 모델 ─────────────────────────────────────────────────────

@CFGS.Register_module("toy_dataset_Config")
@dataclass
class _Toy_Dataset_Config(Dataset_Config):
    config_type: str = "toy_dataset_Config"
    object_type: str = "toy_dataset"


@DATASETS.Register_module("toy_dataset")
class _Toy_Dataset(Custom_Dataset):
    """특징 4 개, 클래스는 첫 특징의 구간 - 배울 수 있는 규칙."""

    def Builder(self, data_dir: str, name: str, category: str, size: int = 32, classes: int = 3, seed: int = 0, **_):
        _gen = torch.Generator().manual_seed(seed)
        self.x = torch.rand(size, 4, generator=_gen)
        self.y = torch.clamp((self.x[:, 0] * classes).long(), max=classes - 1)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return {"x": self.x[index], "y": self.y[index]}

    def Info_for_onnx(self):
        _profile = {"name": "x", "dtype": "float32", "min_shape": [1, 4], "opt_shape": [8, 4], "max_shape": [32, 4]}
        return (None, (torch.zeros(1, 4),), {"input_names": ["x"], "output_names": ["logits"]},
                {"input_profiles": [_profile], "output_profiles": []})


@CFGS.Register_module("toy_model_Config")
@dataclass
class _Toy_Model_Config(Trainable_Model_Config):
    config_type: str = "toy_model_Config"
    object_type: str = "toy_model"
    in_dim: int = 4
    classes: int = 3


@MODELS.Register_module("toy_model")
class _Toy_Model(Trainable_Model):
    def Build(self, in_dim: int, classes: int, **_):
        self.net = nn.Sequential(nn.Linear(in_dim, 16), nn.ReLU(), nn.Linear(16, classes))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ── job, runner ─────────────────────────────────────────────────────────────

@_JOBS.Register_module("learning")
class _Learning(Supervised_Learning_Job):
    resume_selection = None
    eval_selection = _BEST

    def _Forward(self, batch, device, is_train, model, loss_fn=None, **kwargs):
        _x, _y = batch["x"].to(device), batch["y"].to(device)
        _logits = model(_x)
        _n = len(_y)
        _acc = float((_logits.argmax(1) == _y).float().mean())
        _out: dict[str, Any] = {"accuracy": (_acc, _n)}
        _loss = None
        if loss_fn is not None:
            _loss, _detail = loss_fn({"logits": _logits}, {"logits": _y})
            _out["loss"] = (float(_loss.detach()), _n)
        return _loss, _n, _out


@_JOBS.Register_module("early")
class _Early(_Learning):
    def _Should_stop(self, current_iter: int, metric: Any) -> bool:
        return current_iter >= 0


@_JOBS.Register_module("broken")
class _Broken(_Learning):
    def _Forward(self, batch, device, is_train, model, loss_fn=None, **kwargs):
        raise RuntimeError("forward broke")


@_JOBS.Register_module("export")
class _Export(Export_Job):
    Assembler = Supervised_Assembler
    eval_selection = _BEST

    def _Prepare_export_artifacts(self, device, save_path: Path, export: Export_Config, model, datasets, **_):
        _, _dummy, _onnx_kw, _rt = datasets[Mode.TEST].Info_for_onnx()
        _onnx_cfg = {"f": str(save_path / "toy.onnx"), "opset_version": export.opset_version,
                     "do_constant_folding": export.do_constant_folding, "dynamo": False, **_onnx_kw}
        _rt_cfg = {"onnx_file": "toy.onnx", "precision": export.precision, "workspace_size_mb": export.size_mb, **_rt}
        return model.eval(), tuple(_d.to(device) for _d in _dummy), "toy", _onnx_cfg, _rt_cfg


@dataclass
class _Toy_Config(Supervised_Config):
    pass


class _Toy_Runner(Torch_Runner):
    config: _Toy_Config
    JOB_REGISTRY = _JOBS


def _Events(result_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (result_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_gpu_runner_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "RESULT_ROOT", str(tmp_path))
    _base = [str(_RES / "hub.yaml"), f"{_RES / 'model.yaml'}@model", f"{_RES / 'loss.yaml'}@loss",
             f"{_RES / 'optim.yaml'}@optim"]

    # step : learning - iterations, checkpoints, metric json, metric records, saved config
    _first = _Toy_Runner.From_argv(_base)
    assert _first.config.model.classes == 3, "learning: shared value into the model"
    assert _first.Run() is True, "learning: finished without error records"
    _dir = _first.result_dir
    assert sorted(_p.name for _p in (_dir / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt", "checkpoint_1.pt", "checkpoint_2.pt"], "learning: checkpoint per iteration"
    assert (_dir / "avg" / "val" / "scalar" / "iter_2.json").is_file(), "learning: val metric json"
    _metric = [_e for _e in _Events(_dir) if _e["name"] == "metric"]
    assert len(_metric) == 3 and "val/accuracy" in _metric[-1] and "train/loss" in _metric[-1], \
        "learning: one metric record per iteration with mode/name keys"
    assert (_dir / "config.yaml").is_file(), "learning: config saved"

    # step : resume learning - continues from the last checkpoint up to the new max
    _resume = f"resume={_dir}"
    _more = _Toy_Runner.From_argv([*_base, _resume, "max_iters=5"])
    assert _more.Run() is True and (_dir / "checkpoints" / "checkpoint_4.pt").is_file(), \
        "resume: continued to the new max"
    _iters = [_e["iter"] for _e in _Events(_dir) if _e["name"] == "metric"]
    assert _iters[-2:] == [3, 4], f"resume: started after the last checkpoint {_iters}"
    with pytest.raises(ValueError):
        _Toy_Runner.From_argv([*_base, _resume, "optim.base_lr=0.5"])

    # step : test - one pass on the test mode with the best val checkpoint
    _best = _BEST(_dir)
    _test = _Toy_Runner.From_argv([*_base, _resume, "test=true"])
    assert _test.Run() is True, "test: finished"
    assert (_dir / "avg" / "test" / "scalar" / f"iter_{_best}.json").is_file(), "test: metric of the picked iteration"

    # step : export - onnx and runtime config in the run dir, the onnx runs
    _export = _Toy_Runner.From_argv([*_base, _resume, "job=export", "export.precision=FP16", "export.opset_version=17"])
    assert _export.Run() is True, "export: finished"
    assert (_dir / "toy.onnx").is_file() and (_dir / "toy_rt_cfg.yaml").is_file(), "export: onnx and runtime config"
    _session = onnxruntime.InferenceSession(str(_dir / "toy.onnx"), providers=["CPUExecutionProvider"])
    _out = _session.run(None, {"x": np.zeros((1, 4), dtype=np.float32)})[0]
    assert _out.shape == (1, 3), "export: onnx gives logits for 3 classes"

    # step : early stop - one iteration, still a success
    _early = _Toy_Runner.From_argv([*_base, "job=early"])
    assert _early.Run() is True, "early: stop is not a failure"
    assert sorted(_p.name for _p in (_early.result_dir / "checkpoints").iterdir()) == ["checkpoint_0.pt"], \
        "early: stopped after the first iteration"

    # step : broken forward - logged with a trace, run fails
    _broken = _Toy_Runner.From_argv([*_base, "job=broken"])
    assert _broken.Run() is False, "broken: run failed"
    _errors = [_e for _e in _Events(_broken.result_dir) if _e["level"] == "ERROR"]
    assert _errors and "forward broke" in _errors[0]["exc"], "broken: error record with the trace"

    Setup_log(None, {"root": Log_Config(level="WARNING", to=[CONSOLE])})
    logging.getLogger("metric").handlers.clear()
