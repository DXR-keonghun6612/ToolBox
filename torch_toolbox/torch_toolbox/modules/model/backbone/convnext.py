from __future__ import annotations
from typing import Literal
from dataclasses import dataclass, field

from .... import CFGS
from ... import MODELS
from .utils.from_timm import Timm_Feature_Backbone, Timm_Feature_Backbone_Config


MODEL_NAME = "convnext"
CONFIG_NAME = f"{MODEL_NAME}_Config"


# ConvNeXt V1 만 둔다. V2(FCMAE) 가중치는 CC BY-NC 라 상업 이용이 막힌다 —
# 구조가 아니라 가중치 라이선스 문제이므로 사전학습을 쓰는 한 우회가 없다.
# 여기 있는 것들은 fb_*(MIT) 와 in12k_*(Apache-2.0) 라 제약이 없다.
_CONVNEXT_VARIANTS = {
    "convnext_atto": "convnext_atto.d2_in1k",
    "convnext_femto": "convnext_femto.d1_in1k",
    "convnext_pico": "convnext_pico.d1_in1k",
    "convnext_nano": "convnext_nano.in12k_ft_in1k",
    "convnext_tiny": "convnext_tiny.in12k_ft_in1k",
    "convnext_small": "convnext_small.in12k_ft_in1k",
    "convnext_base": "convnext_base.fb_in22k_ft_in1k",
    "convnext_large": "convnext_large.fb_in22k_ft_in1k",
    "convnext_xlarge": "convnext_xlarge.fb_in22k_ft_in1k",
}

ConvNeXtVariantType = Literal[
    "convnext_atto", "convnext_femto", "convnext_pico", "convnext_nano",
    "convnext_tiny", "convnext_small", "convnext_base", "convnext_large",
    "convnext_xlarge",
]


@CFGS.Register_module(CONFIG_NAME)
@dataclass
class ConvNeXt_Config(Timm_Feature_Backbone_Config):
    """ConvNeXt 백본 설정. 공통 필드는 베이스가 소유한다.

    Attributes:
        variant: ``_CONVNEXT_VARIANTS`` 의 키.
        out_indices: 네 단 전부. stride 는 순서대로 4 / 8 / 16 / 32.
    """

    config_type: str = CONFIG_NAME
    object_type: str = MODEL_NAME

    variant: ConvNeXtVariantType = "convnext_tiny"
    out_indices: list[int] = field(default_factory=lambda: [0, 1, 2, 3])


@MODELS.Register_module(MODEL_NAME)
class ConvNeXt(Timm_Feature_Backbone):
    """timm 기반 ConvNeXt 백본 래퍼.

    ``trainable_modules`` 로 가리킬 최상위 모듈: ``stem_0`` · ``stem_1`` ·
    ``stages_0`` ~ ``stages_3``.

    Note:
        정규화가 LayerNorm 계열이라 running 통계가 없다 — 얼린 단의 통계가 학습
        환경으로 흘러가는 문제가 구조적으로 없다.
    """

    VARIANTS = _CONVNEXT_VARIANTS
