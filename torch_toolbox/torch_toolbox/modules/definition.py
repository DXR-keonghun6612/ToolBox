from __future__ import annotations
from typing import Any, ClassVar
from dataclasses import dataclass, field

import torch
from torch.nn import Module

from python_toolbox.project.config import Base_Config


@dataclass
class Module_Config_Template(Base_Config):
    """모든 모듈 Config 의 최상위 뼈대.

    Attributes:
        name: 모듈 식별자.
        config_type: `CFGS` 조회 키.
        object_type: 도메인 registry (`MODELS`, `LOSSES` 등) 조회 키.
        trainable: False 면 빌드 후 파라미터 grad 비활성화.
    """

    name: str = "default_name"
    config_type: str = "Config"
    object_type: str = "Model"
    trainable: bool = True


@dataclass
class Composable_Config(Module_Config_Template):
    """서브모듈을 선언하는 Config.

    Attributes:
        sub_module_meta: 서브모듈 키 -> raw Config dict. `Extract()` 제외,
            `Build_from_registry` 가 `CFGS` 로 인스턴스화.
    """

    __exclude_extract__: ClassVar[set[str]] = {"sub_module_meta"}

    sub_module_meta: dict[str, dict[str, Any]] = field(default_factory=dict)


class Composable_Module(Module):
    """registry 조립 대상 모듈의 추상 기반.

    생성 시 `Build()` 호출. 서브클래스는 `Build()` 와 `forward()` 구현.

    Attributes:
        name: 모듈 식별자. Config 의 `name`.
        trainable: False 면 전 파라미터 `requires_grad` 비활성화.
    """

    def __init__(
        self, name: str,
        trainable: bool = True,
        **build_kwarg
    ) -> None:
        super().__init__()
        self.name = name
        self.trainable = trainable
        self.Build(**build_kwarg)
        if not trainable:
            self.requires_grad_(trainable)

    def Build(self, *arg, **build_kwarg):
        """서브모듈, 레이어 초기화.

        Args:
            **build_kwarg: `Config.Extract()` 의 하이퍼파라미터 + 먼저 빌드된 서브모듈.
        """
        raise NotImplementedError

    def forward(self, *args, **kwarg):
        raise NotImplementedError

    def Out_channels(self) -> list[int]:
        """출력 텐서별 채널 수. 단일 출력도 리스트.

        같은 계층의 형제 모듈이 차원 표현식으로 참조 (`Build_from_registry`).
        참조당하는 모듈만 구현.

        Returns:
            출력 텐서별 채널 수.
        """
        raise NotImplementedError(
            f"{type(self).__name__}에 Out_channels()가 없다. config에서 이 모듈을 "
            f"차원 출처로 참조하려면 구현해야 한다."
        )

    def Load_weights(self, weight_path: str) -> None:
        """사전학습 가중치 부분 로드. `strict=False`, 키 불일치 레이어는 건너뜀.

        Args:
            weight_path: 가중치 파일 경로 (.pt / .pth).
        """
        _state = torch.load(weight_path, map_location="cpu")
        self.load_state_dict(_state, strict=False)
