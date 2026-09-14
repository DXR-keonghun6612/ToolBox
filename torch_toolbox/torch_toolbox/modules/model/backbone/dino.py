from __future__ import annotations
from typing import Any, Literal
from dataclasses import dataclass, field

import timm
import torch.nn as nn

from .... import CFGS
from ... import MODELS
from ...build import Module_Config_Template
from ..definition import Trainable_Model


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
class DINO_Config(Module_Config_Template):
    config_type: str = CONFIG_NAME
    object_type: str = MODEL_NAME
    trainable: bool = False

    variant: DinoVariantType = "v2_vits14"
    # 이 래퍼가 존재하는 이유가 DINO 사전학습 표현이라 기본이 True 다. False 로 만들면
    # frozen 랜덤 ViT 가 되는데, 그건 아무 에러 없이 조용히 학습이 무의미해지는 구성이다.
    pretrained: bool = True
    timm_kwargs: dict[str, Any] = field(default_factory=dict)
    # trainable=False일 때 전체 freeze 후 이 목록의 모듈만 unfreeze (가중치는 보존)
    trainable_modules: list[str] = field(default_factory=list)
    # 꺼낼 블록 인덱스. 비우면 마지막 블록만(기존 동작).
    #
    # ViT 는 해상도를 유지한 채 블록마다 표현이 달라진다 — 얕을수록 국소·위치 정보가,
    # 깊을수록 의미가 강하다. 마지막 하나만 쓰면 dense prediction 이 필요로 하는 국소
    # 정보를 버리는데, **frozen 백본에서는 그게 순손실이다**: 중간 블록은 어차피
    # 계산되고, 꺼내 써도 학습 파라미터가 늘지 않는다.
    # 여러 단을 지정하면 forward 가 그만큼의 텐서를 내므로 소비하는 쪽이 합쳐야 한다
    # (Out_channels() 도 단마다 하나씩 낸다 → config 의 {sum: [...]} 로 폭을 도출).
    out_indices: list[int] = field(default_factory=list)


@MODELS.Register_module(MODEL_NAME)
class DINO(Trainable_Model):
    """timm 라이브러리를 기반으로 DINO 모델을 불러오는 백본 래퍼."""

    backbone: nn.Module

    def __init__(
        self,
        name: str,
        trainable: bool = False,
        trainable_modules: list[str] | None = None,
        **build_kwarg,
    ) -> None:
        super().__init__(name, trainable, **build_kwarg)
        # Composable_Module이 전체 freeze를 적용한 뒤 지정 모듈만 unfreeze 한다.
        # **가중치는 건드리지 않는다** — 사전학습 표현을 남겨두고 미세조정하는 것이 목적이다.
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
        """timm 에서 DINO 백본을 만든다.

        Args:
            variant: ``_DINO_VARIANTS`` 의 키.
            pretrained: DINO 사전학습 가중치 로드 여부. 기본 True.
            timm_kwargs: ``timm.create_model`` 추가 인자 (``img_size``·``in_chans`` 등).
                ``pretrained`` 는 여기 넣지 않는다 — 위 인자가 정본이다.
            out_indices: 꺼낼 블록 인덱스. None/빈 리스트면 마지막 블록만.
                근거는 :class:`DINO_Config` 의 같은 이름 필드 참조.

        Raises:
            ValueError: 알 수 없는 variant, ``pretrained`` 중복 지정,
                또는 ``out_indices`` 가 블록 범위를 벗어난 경우.
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
        """꺼내는 단마다 하나씩. ``out_indices`` 가 비면 항목 하나다.

        ``features_only`` 가 아니라 ``timm.create_model(num_classes=0)`` 으로 만들어
        ``feature_info`` 대신 ``num_features`` 가 출력 차원이다. ViT 는 모든 블록이 같은
        폭이라 단이 몇 개든 값은 같다 — 소비하는 쪽이 합칠 때 폭이 필요해서 개수를 맞춘다.
        """
        return [int(self.backbone.num_features)] * max(len(self.out_indices), 1)

    def Feature_strides(self) -> list[int]:
        """단별 출력 stride. ViT 는 전 블록이 같은 격자라 어느 단이든 patch 크기다.

        소비하는 쪽이 다단을 합칠 때 "어느 단이 어느 해상도인가"를 물어야 하는데,
        CNN 백본은 단마다 다르고 ViT 는 전부 같다 — 그 차이를 소비처가 분기로 알지
        않도록 양쪽이 같은 형태로 답한다.
        """
        _ph, _ = self.backbone.patch_embed.patch_size
        return [int(_ph)] * max(len(self.out_indices), 1)

    def forward(self, x, **kwarg):
        if self.out_indices:
            # 중간 블록 추출. reshape=True 면 prefix 토큰 제거와 (B,D,H,W) 재배치까지
            # timm 이 하고, norm=True 로 최종 LayerNorm 을 태워 단들의 스케일을 맞춘다
            # (안 태우면 얕은 블록의 분산이 커 concat 뒤 한쪽이 지배한다).
            return list(self.backbone.get_intermediate_layers(
                x, n=self.out_indices, reshape=True, norm=True))

        tokens = self.backbone.forward_features(x)      # (B, prefix + N, D)

        # CLS(1) + register(reg 변형은 4) 등 prefix 토큰 제거 → (B, N, D)
        num_prefix = getattr(self.backbone, "num_prefix_tokens", 1)
        patches = tokens[:, num_prefix:]

        B, N, D = patches.shape
        ph, pw = self.backbone.patch_embed.patch_size
        H, W = x.shape[-2] // ph, x.shape[-1] // pw     # 비정사각 입력 대응
        if H * W != N:
            raise ValueError(
                f"패치 격자({H}x{W}={H * W})와 토큰 수({N})가 불일치합니다. "
                f"입력 크기 {tuple(x.shape[-2:])}가 패치 크기 {(ph, pw)}의 배수인지 확인하세요."
            )

        spatial = patches.permute(0, 2, 1).reshape(B, D, H, W)  # (B, D, H, W)
        return [spatial]
