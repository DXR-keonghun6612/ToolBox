from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor

"""2D 커널과 그 채널별 합성곱. 커널 생성은 여기, 커널 뱅크 state 는 `transform.filter.Filter`."""


_SOBEL_X = ((-1.0, 0.0, 1.0), (-2.0, 0.0, 2.0), (-1.0, 0.0, 1.0))
_SOBEL_Y = ((-1.0, -2.0, -1.0), (0.0, 0.0, 0.0), (1.0, 2.0, 1.0))


def Sobel_kernels() -> tuple[Tensor, Tensor]:
    """Sobel x, y 커널. 각각 (3, 3) float32."""
    return torch.tensor(_SOBEL_X), torch.tensor(_SOBEL_Y)


def Log_sharpen_kernel(*, sigma: float, size: int, strength: float) -> Tensor:
    """샤프닝 커널 `delta - strength * LoG(sigma)`.

    LoG 는 합 0 이라 합 1 = DC 보존 -> 정규화와 교환 가능. (sharpen(x) - m) / s == sharpen((x - m) / s).
    부호 : LoG 는 밝은 능선 중심에서 음수라 빼면 능선 강화.

    Args:
        sigma: 가우시안 표준편차 (px, 양수).
        size: 커널 한 변 (3 이상 홀수).
        strength: LoG 배율.

    Returns:
        (size, size) float32.

    Raises:
        ValueError: `size` 가 3 미만 또는 짝수, `sigma` 가 양수 아님.
    """
    if size % 2 == 0 or size < 3:
        raise ValueError(f"size 는 3 이상 홀수: {size}")
    if sigma <= 0:
        raise ValueError(f"sigma 는 양수: {sigma}")

    _ax = torch.arange(size, dtype=torch.float64) - (size - 1) / 2.0
    _yy, _xx = torch.meshgrid(_ax, _ax, indexing="ij")
    _r2 = _xx ** 2 + _yy ** 2
    _s2 = float(sigma) ** 2

    _g = torch.exp(-_r2 / (2.0 * _s2))
    _g = _g / _g.sum()
    _log = (_r2 - 2.0 * _s2) / (_s2 ** 2) * _g
    _log = _log - _log.mean()                # 이산화 오차 보정 -> 합 0

    _delta = torch.zeros(size, size, dtype=torch.float64)
    _delta[size // 2, size // 2] = 1.0
    return (_delta - float(strength) * _log).float()


def Depthwise(x: Tensor, kernels: Tensor) -> Tensor:
    """채널마다 같은 커널 묶음 적용. reflect 패딩, 출력 크기 = 입력 크기.

    Args:
        x: (N, C, H, W).
        kernels: (K, k, k). k 홀수, k // 2 < 입력 변.

    Returns:
        (N, C, K, H, W).
    """
    _n, _h, _w = x.shape[0], x.shape[2], x.shape[3]
    # 채널 수는 Python int. trace 에서 동적이면 conv weight shape 이 미정이라 export 실패
    _c, _k = int(x.shape[1]), int(kernels.shape[0])
    _p = kernels.shape[-1] // 2
    _weight = kernels.to(x).unsqueeze(1).repeat(_c, 1, 1, 1)       # (C*K, 1, k, k), 그룹 c = 채널 c
    _y = F.conv2d(F.pad(x, (_p,) * 4, mode="reflect"), _weight, groups=_c)
    return _y.view(_n, _c, _k, _h, _w)


def Sobel(x: Tensor) -> Tensor:
    """채널별 Sobel 그래디언트.

    Args:
        x: (N, C, H, W).

    Returns:
        (N, C, 2, H, W). [gx, gy].
    """
    return Depthwise(x, torch.stack(Sobel_kernels()))
