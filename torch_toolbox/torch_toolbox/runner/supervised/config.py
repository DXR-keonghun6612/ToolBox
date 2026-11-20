"""지도학습 설정 - torch 실행 설정에 model, loss, optim 하나씩."""
from __future__ import annotations

from dataclasses import dataclass, field

from ...modules.loss.definition import Assemble_Loss_Config
from ...modules.model.definition import Trainable_Model_Config
from ...optim.definition import Optim_Node_Config
from ..config import Torch_Config


@dataclass
class Supervised_Config(Torch_Config):
    """지도학습 실행 설정.

    Attributes:
        model: 모델 설정 - `config_type` 으로 `CFGS` 에서 고름.
        loss: 손실 설정.
        optim: optimizer, scheduler 설정.
    """

    model: Trainable_Model_Config = field(default_factory=Trainable_Model_Config)
    loss: Assemble_Loss_Config = field(default_factory=Assemble_Loss_Config)
    optim: Optim_Node_Config = field(default_factory=Optim_Node_Config)
