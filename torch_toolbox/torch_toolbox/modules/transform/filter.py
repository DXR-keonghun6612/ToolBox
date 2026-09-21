"""2D 커널 필터 layer. state = 커널 뱅크."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor

from ... import CFGS
from .. import MODELS
from ..definition import Composable_Config
from ..model.definition import Trainable_Model

from .functional.filter import Depthwise, Log_sharpen_kernel, Sobel_kernels


_NAME = "filter"
_CFG  = f"{_NAME}_Config"


@CFGS.Register_module(_CFG)
@dataclass
class Filter_Config(Composable_Config):
    """커널 뱅크 설정.

    Attributes:
        log_sigma: LoG 샤프닝 가우시안 표준편차 (px).
        log_kernel_size: LoG 샤프닝 커널 한 변 (3 이상 홀수).
        log_strength: LoG 배율.
    """
    config_type: str = _CFG
    object_type: str = _NAME
    trainable: bool = False
    log_sigma: float = 1.0
    log_kernel_size: int = 7
    log_strength: float = 1.0


@MODELS.Register_module(_NAME)
class Filter(Trainable_Model):
    """채널별 2D 커널 필터. 이름으로 커널을 골라 depthwise conv 한 번.

    - 뱅크 : 커널을 최대 크기로 zero-pad 해 쌓은 `(K, k, k)`. 입력 채널 수를 모름
    - 이름은 뱅크 slice. trace 시점 상수, 요청 안 한 커널은 계산 안 함
    - reflect 패딩 1회. zero-pad 한 작은 커널은 제 크기 reflect 패딩과 같은 값

    이름 :
        sobel_x, sobel_y  Sobel 그래디언트
        log               샤프닝 `delta - log_strength * LoG(log_sigma)`. 합 1, clip 없음
    """

    bank: Tensor

    def Build(
        self,
        log_sigma: float = 1.0,
        log_kernel_size: int = 7,
        log_strength: float = 1.0,
        **kwargs: Any,
    ) -> None:
        _sx, _sy = Sobel_kernels()
        _kernels = {
            "sobel_x": _sx,
            "sobel_y": _sy,
            "log": Log_sharpen_kernel(sigma=log_sigma, size=log_kernel_size, strength=log_strength),
        }
        _k = max(_t.shape[-1] for _t in _kernels.values())
        self.names = tuple(_kernels)
        self.register_buffer(
            "bank",
            torch.stack([F.pad(_t, ((_k - _t.shape[-1]) // 2,) * 4) for _t in _kernels.values()]),
            persistent=False,
        )

    def forward(self, x: Tensor, *names: str) -> dict[str, Tensor]:
        """
        Args:
            x: (N, C, H, W). 커널 한 변 절반 < 입력 변.
            *names: 커널 이름. 하나 이상.

        Returns:
            {이름: (N, C, H, W)}.

        Raises:
            KeyError: 모르는 이름 또는 이름 없음.
        """
        _unknown = [_n for _n in names if _n not in self.names]
        if _unknown or not names:
            raise KeyError(f"커널 이름 {_unknown or '없음'} (가능: {self.names})")
        _idx = [self.names.index(_n) for _n in names]
        _y = Depthwise(x, self.bank[_idx])                              # (N, C, K', H, W)
        return {_n: _y[:, :, _i] for _i, _n in enumerate(names)}
