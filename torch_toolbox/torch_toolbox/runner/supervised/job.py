"""지도학습 learning job - iteration 갈고리를 고정, 사용처는 `_Forward` 하나를 구현."""
from __future__ import annotations

import time
from contextlib import nullcontext
from typing import Any, Callable

import torch
import torch.nn as nn
import torch.optim as optim
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader

from ... import Mode
from ...metric.definition import Assemble_Metric
from ...modules.model.definition import Trainable_Model
from ..job import Learning_Job
from ..utils.log import log_batch, log_iter
from .assembler import Supervised_Assembler
from .config import Supervised_Config

LOSS_FN = Callable[
    [dict[str, Any], dict[str, Any]],
    tuple[torch.Tensor, dict[str, float]]
]


class Supervised_Learning_Job(Learning_Job):
    """지도학습 learning. `_Iter_hook` 고정, 하위는 `_Forward` 를 구현."""

    config: Supervised_Config
    Assembler = Supervised_Assembler

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
        """iteration 하나. mode 마다 batch 를 돎 : `_Forward` -> (학습) backward, grad clip -> `metric.Update`.

        Args:
            dataloaders: mode -> `(use_grad, DataLoader)`.
            loss_fn: `is_test` 면 None 가능.
            metric: mode 별 accumulator. `time`(sample 당 초)과 `grad_norm`(clip 전)이 더해짐.
            **kwargs: `_Forward` 에 그대로.
        """
        _use_amp = self.config.use_amp
        _max_norm = self.config.max_grad_norm
        for _mode, _loader, _is_train in self._Iter_context(
            current_iter, dataloaders, model, scheduler, is_test, rank, metric
        ):
            _total = len(_loader)
            _batch_mon = self.config.mode[_mode.value].batch_monitoring
            for _i, _batch in enumerate(_loader):
                _t_st = time.monotonic()
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
                        _norm = torch.nn.utils.clip_grad_norm_(model.parameters(), _max_norm)
                        _output["grad_norm"] = (float(_norm), _batch_size)
                    scaler.step(optimizer)
                    scaler.update()

                _elapsed = time.monotonic() - _t_st
                if _mode in metric:
                    metric[_mode].Update(time=(_elapsed / _batch_size, _batch_size), **_output)

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
        """mode 마다 model train / eval, grad 문맥. 다 돈 뒤 `scheduler.step`(예외에도), rank 0 은 `log_iter`.

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
            log_iter(current_iter, {_m.value: _a.Finalize() for _m, _a in metric.items()}, self.run_dir)

    def _Forward(
        self,
        batch: dict[str, Any],
        device: torch.device,
        is_train: bool,
        model: nn.Module,
        **kwargs: Any,
    ) -> tuple[torch.Tensor | None, int, dict[str, Any]]:
        """batch 하나 -> `(loss, batch_size, output_dict)`. `output_dict` 는 accumulator 로. 하위 구현."""
        raise NotImplementedError

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
        """`run_dir/checkpoints/checkpoint_{iter}.pt`. key `iter`, `model_state`, `optim_state`, `scaler_state`,
        (scheduler 있으면) `scheduler_state`."""
        _target = model.module if isinstance(model, nn.parallel.DistributedDataParallel) else model
        _checkpoint: dict[str, Any] = {
            "iter": current_iter,
            "model_state": _target.state_dict(),
            "optim_state": optimizer.state_dict(),
            "scaler_state": scaler.state_dict(),
        }
        if scheduler is not None:
            _checkpoint["scheduler_state"] = scheduler.state_dict()

        _save_dir = self.run_dir / "checkpoints"
        _save_dir.mkdir(parents=True, exist_ok=True)
        torch.save(_checkpoint, _save_dir / f"checkpoint_{current_iter}.pt")
