from __future__ import annotations
from typing import Any, cast
from dataclasses import dataclass, field, InitVar

import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.amp.grad_scaler import GradScaler

from python_toolbox.project import Build_config
from pathlib import Path

from ...modules.build import Build_from_registry
from ...modules.model.definition import Trainable_Model, Trainable_Model_Config
from ...modules.loss.definition import Assemble_Loss_Config
from ... import CFGS
from ...modules import MODELS, LOSSES
from ..assembler import Component_Assembler
from ...optim.definition import Optim_Node_Config
from ...optim.build import Build_optim


# ── Assembler ──────────────────────────────────────────────────────────────


@dataclass
class Supervised_Assembler(
    Component_Assembler[
        optim.Optimizer,
        optim.lr_scheduler.LRScheduler | None,
        Trainable_Model,
    ]
):
    """지도학습 단일 model, loss, optim 조립.

    Attributes:
        model_meta, loss_meta, optim_meta: raw Config dict. `shared` 병합.
        model_cfg, loss_cfg, optim_cfg: 인스턴스화된 Config.
    """

    mode_meta: InitVar[dict[str, dict[str, Any]] | None] = None
    model_meta: InitVar[dict[str, Any] | None] = None
    loss_meta: InitVar[dict[str, Any] | None] = None
    optim_meta: InitVar[dict[str, Any] | None] = None

    model_cfg: Trainable_Model_Config = field(init=False)
    loss_cfg: Assemble_Loss_Config = field(init=False)
    optim_cfg: Optim_Node_Config = field(init=False)

    def __post_init__(
        self,
        mode_meta: dict[str, dict[str, Any]] | None,
        model_meta: dict[str, Any] | None,
        loss_meta: dict[str, Any] | None,
        optim_meta: dict[str, Any] | None,
    ) -> None:
        super().__post_init__(mode_meta)
        self.model_cfg = Build_config(
            Trainable_Model_Config, CFGS, (model_meta or {}), **self.shared
        )
        self.loss_cfg = Build_config(
            Assemble_Loss_Config, CFGS, (loss_meta or {}), **self.shared
        )
        self.optim_cfg = Build_config(
            Optim_Node_Config, CFGS, (optim_meta or {}), **self.shared
        )

    def Save_config(self, save_dir: str | Path, **kwarg) -> None:
        """`model_cfg`, `loss_cfg`, `optim_cfg` 를 더해 저장."""
        _extra = {
            "model_cfg": self.model_cfg.Serialize(),
            "loss_cfg": self.loss_cfg.Serialize(),
            "optim_cfg": self.optim_cfg.Serialize(),
            **kwarg
        }
        super().Save_config(save_dir, **_extra)

    def _Build(
        self, device: torch.device, world_size: int, rank: int,
        is_test: bool = False,
    ) -> dict[str, Any]:
        """dataset 먼저 (모델 `context` 의 출처), 다음 model. `is_test` 면 loss, optim, scaler 없음.

        Returns:
            `_Iter_hook` 이 `**components` 로 받는 dict.
        """
        _datasets, _dataloaders, _metric = self._Build_mode_data(is_test, world_size, rank)
        _model = self._Build_model(device, world_size, self._Build_context(_datasets))

        if is_test:
            return {
                "model": _model,
                "datasets": _datasets,
                "dataloaders": _dataloaders,
                "metric": _metric,
            }

        _loss_fn = self._Build_loss(device, self._Build_context(_datasets))
        _optim, _scheduler, _scaler = self._Build_optim_and_scheduler(_model)
        return {
            "model": _model,
            "datasets": _datasets,
            "dataloaders": _dataloaders,
            "loss_fn": _loss_fn,
            "optimizer": _optim,
            "scheduler": _scheduler,
            "scaler": _scaler,
            "metric": _metric,
        }

    def _Build_context(self, datasets: dict[Any, Any]) -> dict[str, Any]:
        """model, loss 의 차원 표현식이 `$키` 로 참조하는 값. 기본 비어 있음, 서브클래스가 dataset 에서 채움."""
        return {}

    def _Build_model(
        self, device: torch.device, world_size: int,
        context: dict[str, Any] | None = None,
    ) -> Trainable_Model:
        """`model_cfg` 조립. `world_size > 1` 이면 DDP 래핑."""
        _model = Build_from_registry(self.model_cfg, MODELS, context).to(device)
        if world_size > 1:
            _local = torch.cuda.current_device()
            _model = nn.parallel.DistributedDataParallel(
                _model, device_ids=[_local], output_device=_local
            )
        return cast(Trainable_Model, _model)

    def _Build_loss(
        self, device: torch.device, context: dict[str, Any] | None = None,
    ) -> nn.Module:
        """`loss_cfg` 조립. `context` 는 model 과 같은 것."""
        return Build_from_registry(self.loss_cfg, LOSSES, context).to(device)

    def _Build_optim_and_scheduler(
        self, model: Trainable_Model,
    ) -> tuple[optim.Optimizer, lr_scheduler.LRScheduler | None, GradScaler]:
        return Build_optim(self.optim_cfg, model, self.use_amp)

    def _Load_checkpoint(self, path: str) -> dict | None:
        """체크포인트 로드. 순수 state_dict 면 `{"model_state": data}` 로 래핑."""
        _data = torch.load(path, map_location="cpu", weights_only=False)
        if not isinstance(_data, dict) or "model_state" not in _data:
            return {"model_state": _data}
        return _data

    def _Load_model_weights(
        self, weight_path: str | None, is_resume: bool,
        model: Trainable_Model, *args, **kwargs: Any,
    ) -> int:
        """가중치 로드 (`strict=False`) -> 시작 이터레이션. resume 이면 체크포인트 `iter + 1`, 아니면 0."""
        if weight_path is None:
            return 0
        _ckpt = self._Load_checkpoint(weight_path)
        if _ckpt is None:
            return 0
        _target = model.module if isinstance(model, nn.parallel.DistributedDataParallel) else model
        _target.load_state_dict(_ckpt["model_state"], strict=False)
        return _ckpt.get("iter", 0) + 1 if is_resume else 0

    def _Restore_train_states(
        self, weight_path: str | None, start_iter: int,
        optimizer: optim.Optimizer,
        scheduler: lr_scheduler.LRScheduler | None,
        scaler: GradScaler,
        *args, **kwargs: Any,
    ) -> None:
        """optimizer, scheduler, scaler 상태 복원. 체크포인트에 없는 키는 skip."""
        if weight_path is None:
            return
        _ckpt = self._Load_checkpoint(weight_path)
        if _ckpt is None:
            return
        if "optim_state" in _ckpt:
            optimizer.load_state_dict(_ckpt["optim_state"])
        if scheduler is not None and "scheduler_state" in _ckpt:
            scheduler.load_state_dict(_ckpt["scheduler_state"])
        if "scaler_state" in _ckpt:
            scaler.load_state_dict(_ckpt["scaler_state"])
