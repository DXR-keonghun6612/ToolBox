from __future__ import annotations
from typing import Any

import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.amp.grad_scaler import GradScaler

from ..modules.model.definition import Trainable_Model
from . import SCHEDULER
from .definition import Optim_Node_Config


_SCALED = 10 ** 10    #: `Get_group_map` 의 정수 키 배율


def Build_optim(
    config: Optim_Node_Config,
    model: Trainable_Model | nn.parallel.DistributedDataParallel,
    use_amp: bool = True,
) -> tuple[optim.Optimizer, lr_scheduler.LRScheduler | None, GradScaler]:
    """`Get_group_map` 의 파라미터 그룹으로 옵티마이저, 스케줄러, GradScaler 조립.

    Args:
        config: 옵티마이저, 스케줄러 설정.
        model: DDP 래퍼 허용.
        use_amp: GradScaler 활성화.

    Returns:
        (optimizer, scheduler | None, scaler).

    Raises:
        ValueError: `optim_name` 없음, 옵티마이저 / 스케줄러 미발견.
    """
    if config.optim_name is None:
        raise ValueError("optim_name이 설정되지 않음")

    _group_map: dict[tuple[int, int], list[Any]] = {}
    _core = model.module if isinstance(model, nn.parallel.DistributedDataParallel) else model
    _core.Get_group_map(config.base_lr, config.base_weight_decay, _group_map, _SCALED)

    _optim_cls = getattr(optim, config.optim_name, None)
    if _optim_cls is None:
        raise ValueError(f"옵티마이저 누락: {config.optim_name}")

    _optimizer: optim.Optimizer = _optim_cls(
        [
            {"params": _p, "lr": _k_lr / _SCALED, "weight_decay": _k_wd / _SCALED}
            for (_k_lr, _k_wd), _p in _group_map.items()
        ],
        **config.optim_kwargs,
    )

    _scheduler = None
    if config.scheduler_name:
        _sched_cls = getattr(lr_scheduler, config.scheduler_name, None)
        if _sched_cls is None:
            _sched_cls = SCHEDULER.Get(config.scheduler_name)
        if _sched_cls is None:
            raise ValueError(f"스케줄러 누락: {config.scheduler_name}")
        _scheduler = _sched_cls(optimizer=_optimizer, **config.scheduler_kwargs)

    return _optimizer, _scheduler, GradScaler(enabled=use_amp)
