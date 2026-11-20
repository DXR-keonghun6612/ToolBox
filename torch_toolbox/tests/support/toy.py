"""GPU 테스트가 함께 쓰는 합성 학습 - 데이터셋, 모델, job, runner 를 등록. DDP 자식이 다시 import 하므로 모듈로 둠.

데이터 : 특징 4 개, 클래스는 첫 특징의 구간 - 배울 수 있는 규칙. 설정 파일은 `tests/resource/gpu/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

import torch_toolbox.metric.component.scalar  # noqa: F401 - scalar_accumulator 등록
from python_toolbox.registry import Registry
from python_toolbox.run.job import Job
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

RES = Path(__file__).parents[1] / "resource" / "gpu"
BEST = Iter_Selection(Max_of, "val", "accuracy")
JOBS = Registry[type[Job]]("torch_toy_job", Job)


def Base_argv() -> list[str]:
    """설정 파일 넷 - hub 는 root, 나머지는 `model`, `loss`, `optim` 아래."""
    return [str(RES / "hub.yaml"), f"{RES / 'model.yaml'}@model", f"{RES / 'loss.yaml'}@loss",
            f"{RES / 'optim.yaml'}@optim"]


@CFGS.Register_module("toy_dataset_Config")
@dataclass
class Toy_Dataset_Config(Dataset_Config):
    config_type: str = "toy_dataset_Config"
    object_type: str = "toy_dataset"


@DATASETS.Register_module("toy_dataset")
class Toy_Dataset(Custom_Dataset):
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
class Toy_Model_Config(Trainable_Model_Config):
    config_type: str = "toy_model_Config"
    object_type: str = "toy_model"
    in_dim: int = 4
    classes: int = 3


@MODELS.Register_module("toy_model")
class Toy_Model(Trainable_Model):
    def Build(self, in_dim: int, classes: int, **_):
        self.net = nn.Sequential(nn.Linear(in_dim, 16), nn.ReLU(), nn.Linear(16, classes))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


@JOBS.Register_module("learning")
class Toy_Learning(Supervised_Learning_Job):
    eval_selection = BEST

    def _Forward(self, batch, device, is_train, model, loss_fn=None, **kwargs):
        _x, _y = batch["x"].to(device), batch["y"].to(device)
        _logits = model(_x)
        _n = len(_y)
        _out: dict[str, Any] = {"accuracy": (float((_logits.argmax(1) == _y).float().mean()), _n)}
        _loss = None
        if loss_fn is not None:
            _loss, _ = loss_fn({"logits": _logits}, {"logits": _y})
            _out["loss"] = (float(_loss.detach()), _n)
        return _loss, _n, _out


@JOBS.Register_module("early")
class Toy_Early(Toy_Learning):
    def _Should_stop(self, current_iter: int, metric: Any) -> bool:
        return current_iter >= 0


@JOBS.Register_module("broken")
class Toy_Broken(Toy_Learning):
    def _Forward(self, batch, device, is_train, model, loss_fn=None, **kwargs):
        raise RuntimeError("forward broke")


@JOBS.Register_module("export")
class Toy_Export(Export_Job):
    Assembler = Supervised_Assembler
    eval_selection = BEST

    def _Prepare_export_artifacts(self, device, save_path: Path, export: Export_Config, model, datasets, **_):
        _, _dummy, _onnx_kw, _rt = datasets[Mode.TEST].Info_for_onnx()
        _onnx_cfg = {"f": str(save_path / "toy.onnx"), "opset_version": export.opset_version,
                     "do_constant_folding": export.do_constant_folding, "dynamo": False, **_onnx_kw}
        _rt_cfg = {"onnx_file": "toy.onnx", "precision": export.precision, "workspace_size_mb": export.size_mb, **_rt}
        return model.eval(), tuple(_d.to(device) for _d in _dummy), "toy", _onnx_cfg, _rt_cfg


class Toy_Runner(Torch_Runner):
    config: Supervised_Config
    JOB_REGISTRY = JOBS
