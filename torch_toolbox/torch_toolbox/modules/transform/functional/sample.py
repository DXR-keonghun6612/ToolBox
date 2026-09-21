from __future__ import annotations

import torch
from torch import Tensor

"""격자 변환. 정수 격자점 gather.

- 정수 격자점은 `Gather` 로 읽음. `GridSample` 없음 (TRT INT8 불가)
- 범위 밖은 0
"""


def Gather_points(flat: Tensor, row: Tensor, col: Tensor, h: int, w: int) -> Tensor:
    """평탄화 마스크에서 정수 격자점을 읽음. 범위 밖은 0.

    Args:
        flat: (B, H*W).
        row, col: (B, P) long. 격자점 좌표.
        h, w: 원래 캔버스 크기.

    Returns:
        (B, P).

    Raises:
        ValueError: `flat` 길이 != h * w. stride 가 틀어지면 유효 범위 안에서 엉뚱한 화소를 읽어 조용히 틀림.
    """
    if flat.shape[-1] != h * w:
        raise ValueError(
            f"flat 길이 {flat.shape[-1]} != h*w ({h}*{w}={h * w}). 입력이 (B, 1, H, W) 인지 확인할 것.")
    _valid = (row >= 0) & (row < h) & (col >= 0) & (col < w)
    _idx = row.clamp(0, h - 1) * w + col.clamp(0, w - 1)
    return flat.gather(1, _idx) * _valid.to(flat.dtype)
