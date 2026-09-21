"""theta 축 순환 정합 거리. `Centroid_frame` 정렬의 자기일관성 측정 (같은 마스크를 회전시켜 최적 shift 가
0 이 아닌 비율), `flip_margin` 낮은 표본의 대비책. 정렬 대체 아님.

`min_s ||x - roll(y, s)||` 는 몫공간 위의 metric (삼각부등식 성립). lag 집합 :

    `Flip_lags`   : 180도 (+ 지터) 만 흡수. 회전 판별력 보존
    전체 NT       : 완전 회전 불변
"""
from __future__ import annotations

import torch
from torch import Tensor


def Circular_correlation(a: Tensor, b: Tensor) -> Tensor:
    """theta 축 순환 상호상관 `out[..., s] = <a, roll(b, s, dim=-1)>` (r 합산). NR 합산은 주파수영역에서.

    Args:
        a: (B, NR, NT).
        b: (M, NR, NT).

    Returns:
        (B, M, NT).
    """
    _nt = a.shape[-1]
    _fa = torch.fft.rfft(a.float(), dim=-1)                        # (B, NR, K)
    _fb = torch.fft.rfft(b.float(), dim=-1)                        # (M, NR, K)
    _c = torch.einsum("brk,mrk->bmk", _fa, _fb.conj())             # (B, M, K)
    return torch.fft.irfft(_c, n=_nt, dim=-1)


def Flip_lags(num_angular: int, width: int = 0, device: torch.device | None = None) -> Tensor:
    """`{0, NT/2}` 각각 `+-width` bin -> `(2*width+1) * 2` lag. 주축각은 mod pi 라 상대 shift 는 0 또는 NT/2.

    Raises:
        ValueError: `num_angular` 홀수.
    """
    if num_angular % 2 != 0:
        raise ValueError(f"num_angular 는 짝수여야 180° 가 정확한 shift 다: {num_angular}")
    _w = torch.arange(-width, width + 1, device=device)
    return torch.cat([_w, _w + num_angular // 2]) % num_angular


def Circular_align_d2(a: Tensor, b: Tensor, lags: Tensor | None = None) -> Tensor:
    """순환 정합 제곱거리 `min_s ||a - roll(b, s)||^2 = ||a||^2 + ||b||^2 - 2 max_s corr(s)`.

    Args:
        a: (B, NR, NT). theta 가 마지막 축.
        b: (M, NR, NT).
        lags: shift 집합. None 이면 전체 NT.

    Returns:
        (B, M) float.
    """
    _corr = Circular_correlation(a, b)                             # (B, M, NT)
    if lags is not None:
        _corr = _corr.index_select(-1, lags.to(_corr.device))
    _ea = a.float().pow(2).sum(dim=(-2, -1)).unsqueeze(1)          # (B, 1)
    _eb = b.float().pow(2).sum(dim=(-2, -1)).unsqueeze(0)          # (1, M)
    return (_ea + _eb - 2.0 * _corr.amax(dim=-1)).clamp_min(0.0)

