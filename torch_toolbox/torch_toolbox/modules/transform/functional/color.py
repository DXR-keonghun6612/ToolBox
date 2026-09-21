from __future__ import annotations

import torch
from torch import Tensor

"""화소 단위 색 연산. 이웃 없음."""


LUMA_REC601 = (0.299, 0.587, 0.114)


def Luma(x: Tensor, *, weight: tuple[float, float, float]) -> Tensor:
    """RGB 가중합 휘도.

    Args:
        x: (N, 3, H, W) RGB.
        weight: 채널 가중치. 예 `LUMA_REC601`.

    Returns:
        (N, 1, H, W).
    """
    _w = torch.tensor(weight, dtype=x.dtype, device=x.device).view(1, 3, 1, 1)
    return (x * _w).sum(dim=1, keepdim=True)


def Saturation(x: Tensor, *, level: float) -> Tensor:
    """최대 채널의 `level` ~ 1 선형 램프.

    Args:
        x: (N, C, H, W) [0, 1]. 정규화 전 raw.
        level: 램프 시작 [0, 1).

    Returns:
        (N, 1, H, W) [0, 1]. 1 = 포화.

    Raises:
        ValueError: `level` 이 [0, 1) 밖.
    """
    if not 0.0 <= level < 1.0:
        raise ValueError(f"level 은 [0, 1): {level}")
    return ((x.amax(dim=1, keepdim=True) - level) / (1.0 - level)).clamp(0.0, 1.0)


def Color_log_ratio(x: Tensor, *, eps: float) -> Tensor:
    """색비 log. 곱셈적 밝기 변화에 불변.

    Args:
        x: (N, 3, H, W) RGB [0, 1].
        eps: 분자, 분모에 더하는 하한. 저휘도에서 비가 잡음이 되는 것 방지.

    Returns:
        (N, 2, H, W). [log(G/R), log(B/G)].
    """
    _r, _g, _b = x[:, 0:1] + eps, x[:, 1:2] + eps, x[:, 2:3] + eps
    return torch.cat([torch.log(_g / _r), torch.log(_b / _g)], dim=1)
