from __future__ import annotations
from typing import Any, Literal
from dataclasses import dataclass, field

import timm
import torch.nn as nn

from .... import CFGS
from ... import MODELS
from ..definition import Trainable_Model, Trainable_Model_Config


MODEL_NAME = "dino"
CONFIG_NAME = f"{MODEL_NAME}_Config"

_DINO_VARIANTS = {
    # DINOv2 (LVD-142M)
    "v2_vits14": "vit_small_patch14_dinov2.lvd142m",
    "v2_vitb14": "vit_base_patch14_dinov2.lvd142m",
    "v2_vitl14": "vit_large_patch14_dinov2.lvd142m",
    "v2_vitg14": "vit_giant_patch14_dinov2.lvd142m",

    # DINOv2 with registers
    "v2_vits14_reg": "vit_small_patch14_reg4_dinov2.lvd142m",
    "v2_vitb14_reg": "vit_base_patch14_reg4_dinov2.lvd142m",
    "v2_vitl14_reg": "vit_large_patch14_reg4_dinov2.lvd142m",
    "v2_vitg14_reg": "vit_giant_patch14_reg4_dinov2.lvd142m",

    # DINOv3
    "v3_vitl16_sat": "vit_large_patch16_dinov3.sat493m",
    "v3_vithp16_lvd": "vit_huge_plus_patch16_dinov3.lvd1689m",
    "v3_vithp16_qkvb_lvd": "vit_huge_plus_patch16_dinov3_qkvb.lvd1689m",
    "v3_vit7b16_lvd": "vit_7b_patch16_dinov3.lvd1689m",
    "v3_vit7b16_sat": "vit_7b_patch16_dinov3.sat493m",
}

DinoVariantType = Literal[
    "v2_vits14", "v2_vitb14", "v2_vitl14", "v2_vitg14",
    "v2_vits14_reg", "v2_vitb14_reg", "v2_vitl14_reg", "v2_vitg14_reg",
    "v3_vitl16_sat", "v3_vithp16_lvd", "v3_vithp16_qkvb_lvd", "v3_vit7b16_lvd", "v3_vit7b16_sat"
]


@CFGS.Register_module(CONFIG_NAME)
@dataclass
class DINO_Config(Trainable_Model_Config):
    """DINO ViT 백본 Config.

    Attributes:
        variant: `_DINO_VARIANTS` 의 키.
        pretrained: 사전학습 가중치 로드 여부. False + `trainable=False` 면 랜덤 특징 고정.
        timm_kwargs: `timm.create_model` 추가 인자 (`img_size`, `in_chans` 등). `pretrained` 는 실패.
        trainable_modules: `trainable=False` 일 때 전체 freeze 후 unfreeze 할 `backbone` 하위
            모듈 이름 접두사. 가중치 보존.
        out_indices: 꺼낼 블록 인덱스. 비면 마지막 블록만. `Out_channels()`,
            `Feature_strides()` 가 단마다 하나씩.
    """

    config_type: str = CONFIG_NAME
    object_type: str = MODEL_NAME
    trainable: bool = False

    variant: DinoVariantType = "v2_vits14"
    pretrained: bool = True
    timm_kwargs: dict[str, Any] = field(default_factory=dict)
    trainable_modules: list[str] = field(default_factory=list)
    out_indices: list[int] = field(default_factory=list)


@MODELS.Register_module(MODEL_NAME)
class DINO(Trainable_Model):
    """timm DINO ViT 백본 래퍼. 출력은 (B, D, H, W) 공간 feature."""

    backbone: nn.Module

    def __init__(
        self,
        name: str,
        trainable: bool = False,
        trainable_modules: list[str] | None = None,
        **build_kwarg,
    ) -> None:
        super().__init__(name, trainable, **build_kwarg)
        # super().__init__() 의 전체 freeze 뒤에 부분 unfreeze. 가중치는 그대로
        if not trainable and trainable_modules:
            for mod_name, module in self.backbone.named_modules():
                for prefix in trainable_modules:
                    if mod_name == prefix or mod_name.startswith(f"{prefix}."):
                        for param in module.parameters(recurse=False):
                            param.requires_grad_(True)
                        break

    def Build(
        self,
        variant: str,
        pretrained: bool = True,
        timm_kwargs: dict[str, Any] | None = None,
        out_indices: list[int] | None = None,
        **build_kwarg
    ) -> None:
        """
        Args:
            variant: `_DINO_VARIANTS` 의 키.
            pretrained: 사전학습 가중치 로드 여부.
            timm_kwargs: `timm.create_model` 추가 인자.
            out_indices: 꺼낼 블록 인덱스. None / 빈 리스트면 마지막 블록만.

        Raises:
            ValueError: 모르는 variant, `timm_kwargs` 에 `pretrained`, 블록 범위 밖 `out_indices`.
        """
        if variant not in _DINO_VARIANTS:
            raise ValueError(f"Unsupported DINO variant '{variant}'")

        _kwargs = dict(timm_kwargs or {})
        if "pretrained" in _kwargs:
            raise ValueError(
                "'pretrained' 는 timm_kwargs 가 아니라 config 의 pretrained 필드로 준다 "
                "(두 곳에 두면 어느 쪽이 이겼는지 보이지 않는다)."
            )

        self.backbone = timm.create_model(
            _DINO_VARIANTS[variant],
            pretrained=pretrained,
            num_classes=0,
            **_kwargs
        )

        self.out_indices = [int(_i) for _i in (out_indices or [])]
        _depth = len(self.backbone.blocks)
        for _i in self.out_indices:
            if not -_depth <= _i < _depth:
                raise ValueError(
                    f"out_indices 의 {_i} 가 블록 범위를 벗어남 "
                    f"(variant '{variant}' 의 블록 수 {_depth})."
                )

    def Out_channels(self) -> list[int]:
        """단마다 `num_features`. 전 블록 같은 폭. `out_indices` 가 비면 하나."""
        return [int(self.backbone.num_features)] * max(len(self.out_indices), 1)

    def Feature_strides(self) -> list[int]:
        """단마다 patch 크기. 전 블록 같은 격자. `out_indices` 가 비면 하나."""
        _ph, _ = self.backbone.patch_embed.patch_size
        return [int(_ph)] * max(len(self.out_indices), 1)

    def forward(self, x, **kwarg):
        if self.out_indices:
            # norm=True : 최종 LayerNorm 을 태워 단 사이 스케일 정합
            return list(self.backbone.get_intermediate_layers(
                x, n=self.out_indices, reshape=True, norm=True))

        tokens = self.backbone.forward_features(x)      # (B, prefix + N, D)

        # prefix = CLS + register 토큰
        num_prefix = getattr(self.backbone, "num_prefix_tokens", 1)
        patches = tokens[:, num_prefix:]

        B, N, D = patches.shape
        ph, pw = self.backbone.patch_embed.patch_size
        H, W = x.shape[-2] // ph, x.shape[-1] // pw
        if H * W != N:
            raise ValueError(
                f"패치 격자({H}x{W}={H * W})와 토큰 수({N})가 불일치합니다. "
                f"입력 크기 {tuple(x.shape[-2:])}가 패치 크기 {(ph, pw)}의 배수인지 확인하세요."
            )

        spatial = patches.permute(0, 2, 1).reshape(B, D, H, W)
        return [spatial]
