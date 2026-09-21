from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from ..definition import Composable_Config, Composable_Module


@dataclass
class Trainable_Model_Config(Composable_Config):
    """학습 하이퍼파라미터를 갖는 모델 Config.

    Attributes:
        lr: 모듈별 학습률 override. None 이면 부모 (최상위는 Assembler 의 base_lr).
        weight_decay: 모듈별 weight decay override. None 이면 부모.
    """

    lr: float | None = None
    weight_decay: float | None = None


class Trainable_Model(Composable_Module):
    """모듈별 lr, weight_decay override 를 갖는 학습 모델의 추상 기반.

    Attributes:
        lr: `Trainable_Model_Config.lr`.
        weight_decay: `Trainable_Model_Config.weight_decay`.
    """

    def __init__(
        self,
        name: str,
        trainable: bool = True,
        lr: float | None = None,
        weight_decay: float | None = None,
        **build_kwarg
    ) -> None:
        # super().__init__() 이 Build() 호출. lr / weight_decay 는 그 전에 할당
        self.lr = lr
        self.weight_decay = weight_decay
        super().__init__(name, trainable, **build_kwarg)

    def Get_group_map(
        self,
        base_lr: float,
        base_weight_decay: float,
        group_map: dict[tuple[int, int], list[Any]],
        scaled_value: int = 10 ** 10
    ) -> None:
        """파라미터 그룹 맵 재귀 구성.

        모듈 트리 DFS. 자식이 `Trainable_Model` 이면 그 모듈의 lr / wd 로 재귀,
        일반 `nn.Module` 이면 현재 lr / wd 로 하위 파라미터 전부 수집.

        Args:
            base_lr: 부모의 학습률.
            base_weight_decay: 부모의 weight decay.
            group_map: `(int(lr * scaled_value), int(wd * scaled_value))` -> 파라미터 리스트.
                호출자가 빈 dict 를 넘기고 in-place 로 채워짐.
            scaled_value: lr, wd 를 정수 키로 바꾸는 배율.
        """
        if (_lr := getattr(self, "lr", None)) is None:
            _lr = base_lr

        if (_wd := getattr(self, "weight_decay", None)) is None:
            _wd = base_weight_decay

        _key = (int(_lr * scaled_value), int(_wd * scaled_value))

        _local_params = [
            _p for _p in self.parameters(recurse=False) if _p.requires_grad
        ]
        if _local_params:
            group_map.setdefault(_key, []).extend(_local_params)

        for _module in self.children():
            if isinstance(_module, Trainable_Model):
                _module.Get_group_map(_lr, _wd, group_map, scaled_value)
            else:
                _standard_params = [
                    _p for _p in _module.parameters(recurse=True) if _p.requires_grad
                ]
                if _standard_params:
                    group_map.setdefault(_key, []).extend(_standard_params)
