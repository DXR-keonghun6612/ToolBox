"""컴포넌트 조립 - 지은 설정으로 프로세스 안에서 dataset, dataloader, metric 을 짓고, 하위가 model, loss, optim 을 더함."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

import torch
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader

from .. import Mode
from ..dataloader.build import Build_dataloader
from ..metric.build import Build_metric
from ..metric.definition import Assemble_Metric, Assemble_Metric_Config
from .config import Torch_Config

MODEL = TypeVar("MODEL")
OPTIM = TypeVar("OPTIM")
SCHEDULER = TypeVar("SCHEDULER")


class Component_Assembler(Generic[OPTIM, SCHEDULER, MODEL]):
    """컴포넌트 조립의 바탕. 하위는 `_Build` 에서 도메인 컴포넌트(model, loss, optim)를 더함.

    Attributes:
        config: runner 가 지은 설정.
    """

    def __init__(self, config: Torch_Config) -> None:
        self.config = config

    def __call__(
        self,
        device: torch.device,
        world_size: int,
        rank: int,
        is_test: bool = False,
        weight_path: str | None = None,
        is_resume: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        """조립 + 가중치 읽기.

        Args:
            is_test: 참이면 optim 없음.
            weight_path: 가중치 경로. 없으면 처음부터.
            is_resume: 참이면 학습 상태(optim, scheduler, scaler)도 되살림.

        Returns:
            (start_iter, components).
        """
        _components = self._Build(device, world_size, rank, is_test)
        _start_iter = self._Load_model_weights(weight_path, is_resume, **_components)

        if not is_test and is_resume:
            self._Restore_train_states(weight_path, _start_iter, **_components)

        return _start_iter, _components

    def Use_grad(self, mode: Mode) -> bool:
        """그 mode 가 기울기를 쓰나 - 설정의 `use_grad` 이고 `train` mode 일 때만."""
        _cfg = self.config.mode.get(mode.value)
        return _cfg is not None and _cfg.use_grad and mode == Mode.TRAIN

    # --- 하위 구현 자리 ---

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

    # --- 공통 짓기 ---

    def _Build_mode_data(
        self, is_test: bool, world_size: int, rank: int,
    ) -> tuple[dict, dict, dict]:
        """mode 별 dataset, dataloader, metric. `is_test` 면 `test` 만, 아니면 `train`, `val`. 설정에 없는 mode 는 건너뜀.

        Returns:
            (datasets, dataloaders, metric). 각각 `Mode` key dict. dataloaders 값은 `(use_grad, DataLoader)`.
        """
        _modes = [Mode.TEST] if is_test else [Mode.TRAIN, Mode.VALIDATION]
        _datasets: dict[Mode, Any] = {}
        _dataloaders: dict[Mode, tuple[bool, DataLoader]] = {}
        _metric: dict[Mode, Assemble_Metric] = {}
        for _mode in _modes:
            _cfg = self.config.mode.get(_mode.value)
            if _cfg is None:
                continue
            _dataset, _loader = Build_dataloader(_cfg.loader, _mode, world_size, rank)
            _datasets[_mode] = _dataset
            _dataloaders[_mode] = (self.Use_grad(_mode), _loader)
            _metric[_mode] = Build_metric(Assemble_Metric_Config(sub_metric_meta=_cfg.metric))
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
