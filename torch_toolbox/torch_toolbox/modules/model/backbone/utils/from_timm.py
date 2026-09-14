from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, ClassVar

import timm
import torch
import torch.nn as nn

from ....definition import Module_Config_Template
from ...definition import Trainable_Model

"""timm ``features_only`` 백본 래퍼의 공통 계약.

변형(variant) 이름표만 다르고 나머지가 같은 래퍼들이 공유한다. 각 래퍼 파일은
``VARIANTS`` 맵과 자기 ``Literal`` 타입·레지스트리 등록만 갖는다.

- ``features_only=True`` 백본만 대상. ``timm.create_model`` 을 직접 쓰는 백본(DINO)은 제외
"""


def load_timm_backbone(
    model_name: str,
    out_indices: list[int] | None = None,
    pretrained: bool = True,
    **timm_kwargs: Any,
) -> nn.Module:
    """timm 에서 ``features_only`` 백본을 만든다.

    Args:
        model_name: timm 모델명 (태그 포함).
        out_indices: 꺼낼 단 인덱스. None 이면 마지막 단만.
        pretrained: 사전학습 가중치 로드 여부.
        **timm_kwargs: ``timm.create_model`` 추가 인자. ``pretrained`` 는 넣지 않는다
            (중복은 호출 전에 ``Timm_Feature_Backbone.Build`` 가 막는다).

    Returns:
        단별 feature map 리스트를 내는 timm ``FeatureListNet``.
    """
    return timm.create_model(
        model_name,
        features_only=True,
        out_indices=out_indices if out_indices is not None else [-1],
        pretrained=pretrained,
        **timm_kwargs,
    )


@dataclass
class Timm_Feature_Backbone_Config(Module_Config_Template):
    """``Timm_Feature_Backbone`` 래퍼 공통 설정.

    각 래퍼 Config 는 이걸 상속해 ``config_type``·``object_type``·``variant`` 와
    자기 ``out_indices`` 기본값만 선언한다.

    Attributes:
        pretrained: 사전학습 가중치 로드 여부. 이 래퍼들이 존재하는 이유가 사전학습
            표현이라 기본이 True 다. False 로 두면 랜덤 초기화 백본이 되는데,
            ``trainable`` 까지 False 면 랜덤 특징을 고정하는 것이라 아무 에러 없이
            조용히 학습이 무의미해진다.
        out_indices: 꺼낼 단 인덱스. 단마다 해상도가 다르므로 소비하는 쪽이 합칠 때
            stride 를 맞춰야 한다 (``Out_channels()`` 는 단마다 하나씩 낸다).
        timm_kwargs: ``timm.create_model`` 추가 인자 (``in_chans`` 등).
            ``pretrained`` 는 위 필드가 정본이라 여기 넣으면 실패한다.
        trainable_modules: ``trainable`` 이 False 일 때 전체 freeze 후 이 목록만
            unfreeze. 가중치는 보존한다 (재초기화 아님). 이름은 ``backbone`` 하위
            모듈 경로이며 접두사로 맞춘다 (예: ConvNeXt ``stages_2`` · ResNet ``layer3``).

            **저수준을 얼리고 고수준을 연다.** 환경 특이성(조명·센서·색)이 배어드는
            자리는 입력에 가까운 단이고, 과제 특이성이 필요한 자리는 깊은 단이다.
            거꾸로 두면 학습 환경의 저수준 통계가 구워져 다른 환경에서 무너진다.
    """

    trainable: bool = False

    pretrained: bool = True
    out_indices: list[int] = field(default_factory=lambda: [0, 1, 2, 3])
    timm_kwargs: dict[str, Any] = field(default_factory=dict)
    trainable_modules: list[str] = field(default_factory=list)


class Timm_Feature_Backbone(Trainable_Model):
    """timm ``features_only`` 백본 래퍼의 공통 구현.

    서브클래스는 ``VARIANTS`` 만 채운다. 빌드·forward·채널 노출·부분 freeze 가 여기 있다.

    Attributes:
        VARIANTS: 공개 variant 이름 -> timm 모델명(태그 포함) 맵.
        frozen_norms: ``train()`` 에서 eval 로 되돌릴 정규화 층.

    Note:
        ``trainable=False`` 면 running 통계를 갖는 정규화 층(BatchNorm 계열)을
        ``train()`` 에서도 eval 로 묶는다. ``requires_grad=False`` 는 통계 갱신을
        막지 못해서, 안 묶으면 "얼렸다" 면서 running 통계만 학습 환경으로 흘러간다 —
        환경이 바뀌면 그대로 어긋난다. LayerNorm 계열(ConvNeXt·Swin)은 해당 없음.
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
            # Composable_Module 이 전체 freeze 를 건 뒤라야 부분 unfreeze 가 의미를 갖는다.
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
            variant: ``VARIANTS`` 의 키.
            pretrained: 사전학습 가중치 로드 여부.
            out_indices: 꺼낼 단 인덱스. None 이면 마지막 단만.
            timm_kwargs: ``timm.create_model`` 추가 인자.

        Raises:
            ValueError: 알 수 없는 variant 이거나, ``timm_kwargs`` 에 ``pretrained`` 가
                중복으로 들어온 경우.
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
        """지정 접두사에 걸리는 모듈만 다시 학습 대상으로 되돌린다.

        가중치는 건드리지 않는다 — 사전학습 표현을 남겨두고 미세조정하는 것이 목적이다.

        Args:
            prefixes: ``backbone`` 하위 모듈 이름 접두사 목록.

        Returns:
            실제로 열린 모듈 이름 집합.

        Raises:
            ValueError: 어떤 모듈에도 안 걸리는 접두사가 있는 경우. 오타가 조용히
                "아무것도 안 열림"으로 지나가면 전부 frozen 인 채로 학습이 돈다.
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
        """열리지 않은 구간의 running 통계 보유 정규화 층.

        Args:
            opened: ``_Unfreeze`` 가 연 모듈 이름 집합.

        Returns:
            ``train()`` 에서 eval 로 묶을 모듈 목록.
        """
        return [
            _module for _name, _module in self.backbone.named_modules()
            if _name not in opened and hasattr(_module, "running_mean")
        ]

    def train(self, mode: bool = True) -> Timm_Feature_Backbone:
        """``mode`` 가 True 여도 얼린 정규화 층은 eval 로 되돌린다."""
        super().train(mode)
        if mode:
            for _module in self.frozen_norms:
                _module.eval()
        return self

    def Out_channels(self) -> list[int]:
        """단별 출력 채널. ``feature_info`` 가 선택된 ``out_indices`` 기준으로 들고 있다."""
        return [int(_c) for _c in self.backbone.feature_info.channels()]

    def Feature_strides(self) -> list[int]:
        """단별 출력 stride (입력 대비 축소 배수).

        단마다 해상도가 다르므로 소비하는 쪽(헤더)이 합칠 때 필요하다 — 채널 수만으로는
        어느 단이 어느 해상도인지 알 수 없다.
        """
        return [int(_r) for _r in self.backbone.feature_info.reduction()]

    def forward(self, x: torch.Tensor, **kwarg: Any) -> list[torch.Tensor]:
        return self.backbone(x)
