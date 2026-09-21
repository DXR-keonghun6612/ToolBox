from __future__ import annotations
from typing import Literal
from dataclasses import dataclass, field

from .... import CFGS
from ... import MODELS
from .utils.from_timm import Timm_Feature_Backbone, Timm_Feature_Backbone_Config


MODEL_NAME = "resnet"
CONFIG_NAME = f"{MODEL_NAME}_Config"


_RESNET_VARIANTS = {
    "resnet18": "resnet18.tv_in1k",
    "resnet34": "resnet34.tv_in1k",
    "resnet50": "resnet50.tv_in1k",
    "resnet101": "resnet101.tv_in1k",

    # 향상된 학습 레시피 (ResNet strikes back)
    "resnet50_v15": "resnet50.a1_in1k",
    "resnet101_v15": "resnet101.a1_in1k",
}

ResNetVariantType = Literal[
    "resnet18", "resnet34", "resnet50", "resnet101",
    "resnet50_v15", "resnet101_v15"
]


@CFGS.Register_module(CONFIG_NAME)
@dataclass
class ResNet_Config(Timm_Feature_Backbone_Config):
    """
    Attributes:
        variant: `_RESNET_VARIANTS` 의 키.
        out_indices: 기본 단 1 ~ 4. stride 4 / 8 / 16 / 32. 0 은 stem (stride 2).
    """

    config_type: str = CONFIG_NAME
    object_type: str = MODEL_NAME

    variant: ResNetVariantType = "resnet50"
    out_indices: list[int] = field(default_factory=lambda: [1, 2, 3, 4])


@MODELS.Register_module(MODEL_NAME)
class ResNet(Timm_Feature_Backbone):
    """`trainable_modules` 최상위 모듈: `conv1`, `bn1`, `layer1` ~ `layer4`. 정규화는 BatchNorm."""

    VARIANTS = _RESNET_VARIANTS
