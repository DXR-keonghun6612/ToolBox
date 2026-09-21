from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor

"""평균 계열 공간 통계. box 창, 가중 평균.

- 합 대신 평균의 비. 600x800 합은 FP16 최대(65504) 초과
- reflect 패딩. 프레임 경계에 인위적 대비 없음. 폭 < 입력 변
"""


_WEIGHT_EPS = 1e-3       #: 가중치 평균 하한. 가중치가 전부 0 일 때 0 나눗셈 방지


def Weighted_mean(v: Tensor, w: Tensor) -> Tensor:
    """공간 가중 평균.

    Args:
        v: (N, C, H, W).
        w: v 로 broadcast 되는 가중치 [0, 1].

    Returns:
        (N, C, 1, 1).
    """
    return ((v * w).mean(dim=(2, 3), keepdim=True)
            / w.mean(dim=(2, 3), keepdim=True).clamp(min=_WEIGHT_EPS))


def Box_mean(v: Tensor, *, window: int) -> Tensor:
    """창 내 평균. 출력 크기 = 입력 크기.

    Args:
        v: (N, C, H, W).
        window: 창 한 변 (홀수).

    Returns:
        (N, C, H, W).
    """
    _p = window // 2
    return F.avg_pool2d(F.pad(v, (_p,) * 4, mode="reflect"), window, stride=1)


def Local_stats(v: Tensor, *, window: int, floor: float) -> tuple[Tensor, Tensor]:
    """창 내 평균과 표준편차. 평균, 제곱평균을 한 번의 pooling 으로.

    Args:
        v: (N, C, H, W).
        window: 창 한 변 (홀수).
        floor: 표준편차 하한. 평탄 영역 노이즈 증폭 방지.

    Returns:
        (mean, std). 각각 (N, C, H, W). std = sqrt(var + floor^2).
    """
    _c = v.shape[1]
    _stat = Box_mean(torch.cat([v, v * v], dim=1), window=window)
    _mean, _sq = _stat[:, :_c], _stat[:, _c:]
    # 부동소수 오차로 분산이 음수가 될 수 있음
    return _mean, torch.sqrt((_sq - _mean * _mean).clamp(min=0.0) + floor ** 2)


def Weighted_lowpass(v: Tensor, w: Tensor, *, pool: int, kernel: int) -> Tensor:
    """가중 정규화 box 저역. 축소 격자에서 box 후 bilinear 복원.

    Args:
        v: (N, C, H, W).
        w: v 로 broadcast 되는 가중치 [0, 1]. 채널마다 따로 정규화.
        pool: 축소 배수.
        kernel: 축소 격자의 box 한 변 (홀수). 절반 < 축소 격자 변.

    Returns:
        (N, C, H, W). box(v * w) / box(w).
    """
    _c = v.shape[1]
    _stat = F.avg_pool2d(torch.cat([v * w, w.expand_as(v)], dim=1), pool, pool)
    _stat = Box_mean(_stat, window=kernel)
    _low = _stat[:, :_c] / _stat[:, _c:].clamp(min=_WEIGHT_EPS)
    return F.interpolate(_low, size=v.shape[-2:], mode="bilinear", align_corners=False)
