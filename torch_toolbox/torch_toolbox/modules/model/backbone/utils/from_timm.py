"""timm `features_only` 백본 래퍼의 공통 구현. 각 래퍼 파일은 `VARIANTS` 맵, `Literal` 타입, registry 등록만."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, ClassVar

import timm
import torch
import torch.nn as nn

from ...definition import Trainable_Model, Trainable_Model_Config


def load_timm_backbone(
    model_name: str,
    out_indices: list[int] | None = None,
    pretrained: bool = True,
    **timm_kwargs: Any,
) -> nn.Module:
    """
    Args:
        model_name: timm 모델명 (태그 포함).
        out_indices: 꺼낼 단 인덱스. None 이면 마지막 단만.
        pretrained: 사전학습 가중치 로드 여부.
        **timm_kwargs: `timm.create_model` 추가 인자. `pretrained` 제외.

    Returns:
        단별 feature map 리스트를 내는 timm `FeatureListNet`.
    """
    return timm.create_model(
        model_name,
        features_only=True,
        out_indices=out_indices if out_indices is not None else [-1],
        pretrained=pretrained,
        **timm_kwargs,
    )


@dataclass
class Timm_Feature_Backbone_Config(Trainable_Model_Config):
    """`Timm_Feature_Backbone` 공통 Config. 래퍼 Config 는 `config_type`, `object_type`, `variant`,
    `out_indices` 기본값만 선언.

    Attributes:
        pretrained: 사전학습 가중치 로드 여부. False + `trainable=False` 면 랜덤 특징 고정.
        out_indices: 꺼낼 단 인덱스. `Out_channels()`, `Feature_strides()` 가 단마다 하나씩.
        timm_kwargs: `timm.create_model` 추가 인자 (`in_chans` 등). `pretrained` 는 실패.
        trainable_modules: `trainable=False` 일 때 전체 freeze 후 unfreeze 할 `backbone` 하위
            모듈 이름 접두사 (예 ConvNeXt `stages_2`, ResNet `layer3`). 가중치 보존.
    """

    trainable: bool = False

    pretrained: bool = True
    out_indices: list[int] = field(default_factory=lambda: [0, 1, 2, 3])
    timm_kwargs: dict[str, Any] = field(default_factory=dict)
    trainable_modules: list[str] = field(default_factory=list)


class Timm_Feature_Backbone(Trainable_Model):
    """timm `features_only` 백본 래퍼. 서브클래스는 `VARIANTS` 만 채움.

    Attributes:
        VARIANTS: 공개 variant 이름 -> timm 모델명 (태그 포함).
        frozen_norms: `train()` 에서 eval 로 되돌리는 정규화 층. `trainable=False` 일 때
            unfreeze 안 된 구간의 running 통계 보유 층 (BatchNorm 계열).
    """

    VARIANTS: ClassVar[dict[str, str]] = {}

    backbone: nn.Module

    def __init__(
        self,
        name: str,
        trainable: bool = False,
        trainable_modules: list[str] | None = None,
        **build_kwarg: Any,
    ) -> None:
        super().__init__(name, trainable, **build_kwarg)

        self.frozen_norms: list[nn.Module] = []
        if not trainable:
            # super().__init__() 의 전체 freeze 뒤에 부분 unfreeze
            self.frozen_norms = self._Stateful_norms(
                self._Unfreeze(trainable_modules or []))
            self.train(self.training)

    def Build(
        self,
        variant: str,
        pretrained: bool = True,
        out_indices: list[int] | None = None,
        timm_kwargs: dict[str, Any] | None = None,
        **build_kwarg: Any,
    ) -> None:
        """
        Args:
            variant: `VARIANTS` 의 키.
            pretrained: 사전학습 가중치 로드 여부.
            out_indices: 꺼낼 단 인덱스. None 이면 마지막 단만.
            timm_kwargs: `timm.create_model` 추가 인자.

        Raises:
            ValueError: 모르는 variant, 또는 `timm_kwargs` 에 `pretrained`.
        """
        if variant not in self.VARIANTS:
            raise ValueError(
                f"Unsupported {type(self).__name__} variant '{variant}'. "
                f"가능한 값: {sorted(self.VARIANTS)}"
            )

        if "pretrained" in (timm_kwargs or {}):
            raise ValueError(
                "'pretrained' 는 timm_kwargs 가 아니라 config 의 pretrained 필드로 준다 "
                "(두 곳에 두면 어느 쪽이 이겼는지 보이지 않는다)."
            )

        self.backbone = load_timm_backbone(
            model_name=self.VARIANTS[variant],
            out_indices=out_indices,
            pretrained=pretrained,
            **(timm_kwargs or {}),
        )

    def _Unfreeze(self, prefixes: list[str]) -> set[str]:
        """접두사에 걸리는 모듈의 `requires_grad` 를 True 로. 가중치는 그대로.

        Args:
            prefixes: `backbone` 하위 모듈 이름 접두사.

        Returns:
            열린 모듈 이름 집합.

        Raises:
            ValueError: 어떤 모듈에도 안 걸리는 접두사.
        """
        _names = {_n for _n, _ in self.backbone.named_modules()}
        _missing = [
            _p for _p in prefixes
            if not any(_n == _p or _n.startswith(f"{_p}.") for _n in _names)
        ]
        if _missing:
            raise ValueError(
                f"trainable_modules {_missing} 가 {type(self).__name__} 의 어떤 모듈에도 "
                f"걸리지 않음. 최상위 모듈: "
                f"{[_n for _n, _ in self.backbone.named_children()]}"
            )

        _opened: set[str] = set()
        for _name, _module in self.backbone.named_modules():
            if any(_name == _p or _name.startswith(f"{_p}.") for _p in prefixes):
                _opened.add(_name)
                for _param in _module.parameters(recurse=False):
                    _param.requires_grad_(True)

        return _opened

    def _Stateful_norms(self, opened: set[str]) -> list[nn.Module]:
        """`opened` 밖의 running 통계 보유 정규화 층.

        Args:
            opened: `_Unfreeze` 가 연 모듈 이름 집합.
        """
        return [
            _module for _name, _module in self.backbone.named_modules()
            if _name not in opened and hasattr(_module, "running_mean")
        ]

    def train(self, mode: bool = True) -> Timm_Feature_Backbone:
        """`mode=True` 여도 `frozen_norms` 는 eval."""
        super().train(mode)
        if mode:
            for _module in self.frozen_norms:
                _module.eval()
        return self

    def Out_channels(self) -> list[int]:
        """`out_indices` 단별 출력 채널."""
        return [int(_c) for _c in self.backbone.feature_info.channels()]

    def Feature_strides(self) -> list[int]:
        """`out_indices` 단별 출력 stride (입력 대비 축소 배수)."""
        return [int(_r) for _r in self.backbone.feature_info.reduction()]

    def forward(self, x: torch.Tensor, **kwarg: Any) -> list[torch.Tensor]:
        return self.backbone(x)
