from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field

import torch
from torch import Tensor
from torch.nn import ModuleDict

from ... import CFGS
from .. import LOSSES
from ..definition import Composable_Config, Composable_Module


LOSS_NAME = "assemble_loss"
CONFIG_NAME = f"{LOSS_NAME}_config"


@CFGS.Register_module(CONFIG_NAME)
@dataclass
class Assemble_Loss_Config(Composable_Config):
    """여러 Loss 의 가중합 Config.

    Attributes:
        sub_loss_coefs: 서브 Loss 이름 -> 계수. 미지정은 1.0.
    """

    config_type: str = CONFIG_NAME
    object_type: str = LOSS_NAME

    sub_loss_coefs: dict[str, float] = field(default_factory=dict)


@LOSSES.Register_module(LOSS_NAME)
class Assemble_Loss(Composable_Module):
    """서브 Loss 의 가중합. pred 에 있는 키만 계산."""

    def Build(
        self,
        sub_loss_coefs: dict[str, float],
        **sub_modules: Any
    ):
        """
        Args:
            sub_loss_coefs: 서브 Loss 이름 -> 계수.
            **sub_modules: `Build_from_registry` 가 주입한 서브 Loss.
        """
        self.loss_modules = ModuleDict()
        self._cached_func: dict[str, tuple[float, Composable_Module]] = {}

        for _name, _module in sub_modules.items():
            _coef = sub_loss_coefs.get(_name, 1.0)
            self.loss_modules[_name] = _module
            self._cached_func[_name] = (_coef, _module)

    def forward(
        self, pred: dict[str, Tensor], target: dict[str, Tensor], **kwarg: Any
    ) -> tuple[Tensor, dict[str, float]]:
        """
        Args:
            pred: 모델 출력. 키 = 서브 Loss 이름.
            target: 정답. pred 와 같은 키.
            **kwarg: 모든 서브 Loss 에 그대로 전달 (예 관심영역 mask). 안 쓰는 Loss 는 `**kwarg` 로 받음.

        Returns:
            (가중합 loss, 서브 Loss 별 값). 값의 키는 `{name}` (raw), `{name}_weighted`.

        Raises:
            KeyError: pred 에 있는 키가 target 에 없음.
        """
        _loss_details: dict[str, float] = {}
        _device = next(iter(pred.values())).device
        _total_loss = torch.tensor(0.0, device=_device)

        for _k, (_coef, _func) in self._cached_func.items():
            if _k not in pred:
                continue
            if _k not in target:
                raise KeyError(
                    f"Assemble_Loss: '{_k}'가 target에 없음. "
                    f"target keys: {list(target.keys())}"
                )

            _raw_loss: Tensor = _func(pred[_k], target[_k], **kwarg)
            _weighted_loss = _coef * _raw_loss
            _total_loss = _total_loss + _weighted_loss

            _loss_details[_k] = _raw_loss.item()
            _loss_details[f"{_k}_weighted"] = _weighted_loss.item()

        return _total_loss, _loss_details
