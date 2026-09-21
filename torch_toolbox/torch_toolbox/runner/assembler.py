from __future__ import annotations
from typing import Any, TypeVar, Generic
from dataclasses import dataclass, field, InitVar
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torch.amp.grad_scaler import GradScaler

from python_toolbox.project import Build_config
from python_toolbox.file import Write_to

from .. import CFGS, Mode
from ..dataloader.definition import Dataloader_Config
from ..dataloader.build import Build_dataloader
from ..metric.definition import Assemble_Metric_Config, Assemble_Metric
from ..metric.build import Build_metric

MODEL = TypeVar("MODEL")
OPTIM = TypeVar("OPTIM")
SCHEDULER = TypeVar("SCHEDULER")


@dataclass
class Component_Assembler(Generic[OPTIM, SCHEDULER, MODEL]):
    """컴포넌트 조립 기반. 서브클래스는 `_Build` 에서 도메인 컴포넌트 (model, loss, optim) 추가.

    Attributes:
        shared: 모든 Config 에 공통 적용하는 필드.
        use_amp: AMP 활성화.
        max_grad_norm: 그래디언트 L2 norm 상한. 0 이면 안 자름. unscale 뒤 적용, 자르기 전 norm 은
            배치 metric `grad_norm`.
        mode_meta: `{mode: {use_grad, loader, metric, batch_monitoring}}`.
        mode_cfg: `mode_meta` 중 선언된 mode 만. `use_grad` 는 TRAIN 만 True.
    """

    shared: dict[str, Any] = field(default_factory=dict)
    use_amp: bool = True
    max_grad_norm: float = 0.0

    mode_meta: InitVar[dict[str, dict[str, Any]] | None] = None

    mode_cfg: dict[str, dict[str, Any]] = field(init=False)

    def __post_init__(
        self,
        mode_meta: dict[str, dict[str, Any]] | None,
    ) -> None:
        self.mode_cfg = {
            _k.value: {**_v, "use_grad": bool(_v.get("use_grad", False)) and _k == Mode.TRAIN}
            for _k in Mode
            if mode_meta and _k.value in mode_meta
            for _v in (mode_meta[_k.value],)
        }

    def Save_config(self, save_dir: str | Path, **kwarg) -> None:
        """조립 설정을 `save_dir/config.yaml` 로.

        Args:
            **kwarg: 서브클래스 추가 항목 (model_cfg, loss_cfg 등).
        """
        _data: dict[str, Any] = {
            "shared": self.shared,
            "use_amp": self.use_amp,
            "max_grad_norm": self.max_grad_norm,
            "mode_cfg": dict(self.mode_cfg),
            **kwarg,
        }
        Write_to(Path(save_dir) / "config.yaml", _data)

    def __call__(
        self,
        device: torch.device,
        world_size: int,
        rank: int,
        is_test: bool = False,
        weight_path: str | None = None,
        is_resume: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        """조립 + 가중치 로드.

        Args:
            is_test: True 면 optim 제외.
            weight_path: 가중치 경로. None 이면 scratch.
            is_resume: True 면 학습 상태 (optim, scheduler, scaler) 도 복원.

        Returns:
            (start_iter, components).
        """
        _components = self._Build(device, world_size, rank, is_test)
        _start_iter = self._Load_model_weights(weight_path, is_resume, **_components)

        if not is_test and is_resume:
            self._Restore_train_states(weight_path, _start_iter, **_components)

        return _start_iter, _components

    # --- 서브클래스 구현 지점 ---

    def _Build(
        self, device: torch.device, world_size: int, rank: int,
        is_test: bool = False,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _Build_model(
        self, device: torch.device, world_size: int,
        context: dict[str, Any] | None = None,
    ) -> MODEL:
        raise NotImplementedError

    # --- 공통 빌드 헬퍼 ---

    def _Build_mode_data(
        self, is_test: bool, world_size: int, rank: int,
    ) -> tuple[dict, dict, dict]:
        """mode 별 dataset, dataloader, metric. `is_test` 면 TEST 만, 아니면 TRAIN, VALIDATION. `mode_cfg` 에 없는 mode 는 skip.

        Returns:
            (datasets, dataloaders, metric). 각각 `Mode` 키 dict. dataloaders 값은 `(use_grad, DataLoader)`.
        """
        _modes = [Mode.TEST] if is_test else [Mode.TRAIN, Mode.VALIDATION]
        _datasets: dict[Mode, Any] = {}
        _dataloaders: dict[Mode, tuple[bool, DataLoader]] = {}
        _metric: dict[Mode, Assemble_Metric] = {}
        for _mode in _modes:
            if _mode.value not in self.mode_cfg:
                continue
            _meta = self.mode_cfg[_mode.value]
            _loader_cfg = Build_config(Dataloader_Config, CFGS, _meta.get("loader", {}), **self.shared)
            _dataset, _loader = Build_dataloader(_loader_cfg, _mode, world_size, rank)
            _datasets[_mode] = _dataset
            _dataloaders[_mode] = (_meta["use_grad"], _loader)
            _metric[_mode] = Build_metric(Assemble_Metric_Config(sub_metric_meta=_meta.get("metric", {})))
        return _datasets, _dataloaders, _metric

    def _Build_loss(self, device: torch.device) -> Any:
        raise NotImplementedError

    def _Build_optim_and_scheduler(
        self, model: MODEL,
    ) -> tuple[OPTIM, SCHEDULER, GradScaler]:
        raise NotImplementedError

    def _Load_model_weights(
        self, weight_path: str | None, is_resume: bool, **components: Any,
    ) -> int:
        return 0

    def _Restore_train_states(
        self, weight_path: str | None, start_iter: int, **components: Any,
    ) -> None:
        pass
