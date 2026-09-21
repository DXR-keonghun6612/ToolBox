from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field

from python_toolbox.project import Base_Config


@dataclass
class Optim_Node_Config(Base_Config):
    """옵티마이저, 스케줄러 Config.

    Attributes:
        optim_name: `torch.optim` 클래스명. 필수.
        base_lr: 기본 학습률. 모듈별 override 는 `Trainable_Model.Get_group_map`.
        base_weight_decay: 기본 weight decay.
        optim_kwargs: lr, weight_decay 제외 옵티마이저 인자.
        scheduler_name: `torch.optim.lr_scheduler` 클래스명 또는 `SCHEDULER` 키. None 이면 없음.
        scheduler_kwargs: optimizer 제외 스케줄러 인자.
    """

    optim_name: str | None = None
    base_lr: float = 1e-4
    base_weight_decay: float = 1e-4
    optim_kwargs: dict[str, Any] = field(default_factory=dict)

    scheduler_name: str | None = None
    scheduler_kwargs: dict[str, Any] = field(default_factory=dict)
