from __future__ import annotations
from typing import Any, Callable
from contextlib import nullcontext

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import torch.optim as optim
from torch.amp.grad_scaler import GradScaler

from python_toolbox.system import Time_Utils

from ... import Mode
from ..utils.log import log_batch, log_iter
from ...modules.model.definition import Trainable_Model
from ...metric.definition import Assemble_Metric
from ..runtime import Base_Runner
from .assembler import Supervised_Assembler


LOSS_FN = Callable[
    [dict[str, Any], dict[str, Any]],
    tuple[torch.Tensor, dict[str, float]]
]


class Supervised_Runner(Base_Runner[Supervised_Assembler, torch.Tensor | None]):
    """지도학습 러너. `_Iter_hook` 고정, 서브클래스는 `_Forward` 구현."""

    def _Iter_hook(
        self,
        current_iter: int,
        device: torch.device,
        *,
        rank: int = 0,
        is_test: bool = False,
        model: Trainable_Model,
        dataloaders: dict[Mode, tuple[bool, DataLoader]],
        loss_fn: LOSS_FN | None = None,
        optimizer: optim.Optimizer | None = None,
        scheduler: optim.lr_scheduler.LRScheduler | None = None,
        scaler: GradScaler | None = None,
        metric: dict[Mode, Assemble_Metric],
        **kwargs: Any,
    ) -> None:
        """iter 하나. mode 마다 batch 순회 : `_Forward` -> (학습) backward, grad clip -> `metric.Update`.

        Args:
            dataloaders: mode -> `(use_grad, DataLoader)`.
            loss_fn: `is_test` 면 None 허용.
            metric: mode 별 accumulator. `time` (sample 당 초) 과 `grad_norm` (clip 전) 이 더해짐.
            **kwargs: `_Forward` 에 그대로 전달.
        """
        _use_amp = self.assembler.use_amp
        _max_norm = self.assembler.max_grad_norm
        for _mode, _loader, _is_train in self._Iter_context(
            current_iter, dataloaders, model, scheduler, is_test, rank, metric
        ):
            _total = len(_loader)
            for _i, _batch in enumerate(_loader):
                _t_st = Time_Utils.Stamp()
                with torch.autocast(device_type=device.type, enabled=_use_amp):
                    _loss, _batch_size, _output = self._Forward(
                        _batch, device, _is_train, model, loss_fn=loss_fn, **kwargs
                    )

                if _is_train and _loss is not None:
                    assert optimizer is not None and scaler is not None
                    optimizer.zero_grad(set_to_none=True)
                    scaler.scale(_loss).backward()
                    if _max_norm > 0:
                        scaler.unscale_(optimizer)
                        _norm = torch.nn.utils.clip_grad_norm_(
                            model.parameters(), _max_norm)
                        _output["grad_norm"] = (float(_norm), _batch_size)
                    scaler.step(optimizer)
                    scaler.update()

                _elapsed = (Time_Utils.Stamp() - _t_st).total_seconds()
                if _mode in metric:
                    metric[_mode].Update(
                        time=(_elapsed / _batch_size, _batch_size), **_output
                    )

                _batch_mon = self.assembler.mode_cfg[_mode.value].get("batch_monitoring")
                if _batch_mon and _mode in metric:
                    log_batch(current_iter, _i, _total, metric[_mode], _batch_mon)

    def _Iter_context(
        self,
        current_iter: int,
        dataloaders: dict[Mode, tuple[bool, DataLoader]],
        model: nn.Module,
        scheduler: optim.lr_scheduler.LRScheduler | None,
        is_test: bool,
        rank: int = 0,
        metric: dict[Mode, Assemble_Metric] | None = None,
    ):
        """mode 마다 model train / eval, grad 컨텍스트. 전부 돈 뒤 `scheduler.step` (예외에도), rank 0 은 `log_iter`.

        Yields:
            (mode, loader, is_train).
        """
        try:
            for _mode, (_use_grad, _loader) in dataloaders.items():
                _is_train = _use_grad and not is_test
                model.train() if _is_train else model.eval()
                with nullcontext() if _is_train else torch.no_grad():
                    yield _mode, _loader, _is_train
        finally:
            if not is_test and scheduler is not None:
                scheduler.step()
        if rank == 0 and metric is not None:
            log_iter(
                current_iter,
                {_m.value: _a.Finalize() for _m, _a in metric.items()},
                self.workspace,
            )

    def _Forward(
        self,
        batch: dict[str, Any],
        device: torch.device,
        is_train: bool,
        model: nn.Module,
        **kwargs: Any,
    ) -> tuple[torch.Tensor | None, int, dict[str, Any]]:
        raise NotImplementedError

    def _Should_stop(
        self, current_iter: int, metric: dict[Mode, Assemble_Metric]
    ) -> bool:
        return False

    def _Save_checkpoint(
        self,
        current_iter: int,
        *,
        rank: int = 0,
        model: Trainable_Model,
        optimizer: optim.Optimizer,
        scheduler: optim.lr_scheduler.LRScheduler | None,
        scaler: GradScaler,
        **kwargs: Any,
    ) -> None:
        """`workspace/checkpoints/checkpoint_{iter}.pt`. 키 `iter`, `model_state`, `optim_state`, `scaler_state`,
        (scheduler 있으면) `scheduler_state`."""
        _target = (
            model.module
            if isinstance(model, nn.parallel.DistributedDataParallel)
            else model
        )
        _checkpoint: dict[str, Any] = {
            "iter": current_iter,
            "model_state": _target.state_dict(),
            "optim_state": optimizer.state_dict(),
            "scaler_state": scaler.state_dict(),
        }
        if scheduler is not None:
            _checkpoint["scheduler_state"] = scheduler.state_dict()

        _save_dir = self.workspace / "checkpoints"
        _save_dir.mkdir(parents=True, exist_ok=True)
        torch.save(_checkpoint, _save_dir / f"checkpoint_{current_iter}.pt")

