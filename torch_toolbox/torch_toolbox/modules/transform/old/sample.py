from __future__ import annotations

import torch
from torch import Tensor
from torch.nn import functional as F

from ..functional.sample import Gather_points

"""소비처 없는 격자 변환. 크롭, 리샘플 + 재이진화.

- `Center_crop` : 서술자가 캔버스 무관이 되어 크롭 경로가 사라짐
- `Resize_binarize` : `px_size` 가 리샘플을 대신함
"""


def Center_crop(mask: Tensor, center: Tensor, *, size: int) -> Tensor:
    """중심점 기준 정사각 정수 창. 보간 없음, 경계 밖 0.

    Args:
        mask: (B, 1, H, W).
        center: (B, 2) long. 창 중심 (col, row), 입력 좌표. `Frame.origin` 과 같은 규약.
        size: 창 한 변 (px).

    Returns:
        (B, 1, size, size). 값 스케일 유지.
    """
    _b = mask.shape[0]
    _h, _w = int(mask.shape[-2]), int(mask.shape[-1])
    _off = torch.arange(size, device=mask.device) - size // 2                # (S,)
    _cols = (center[:, 0].view(_b, 1, 1) + _off.view(1, 1, size)).expand(_b, size, size)
    _rows = (center[:, 1].view(_b, 1, 1) + _off.view(1, size, 1)).expand(_b, size, size)
    _out = Gather_points(mask.reshape(_b, -1), _rows.reshape(_b, -1), _cols.reshape(_b, -1), _h, _w)
    return _out.reshape(_b, 1, size, size)


def Resize_binarize(mask: Tensor, *, size: tuple[int, int], thresh: float) -> Tensor:
    """bilinear 리샘플 후 재이진화. `align_corners=False` = cv2 half-pixel 규약.

    Args:
        mask: (B, 1, H, W) {0, 1}.
        size: 출력 (H, W).
        thresh: 재이진화 임계. 이 값 초과 = 1.

    Returns:
        (B, 1, size[0], size[1]) {0, 1}.
    """
    _r = F.interpolate(mask, size=size, mode="bilinear", align_corners=False)
    return (_r > thresh).to(mask.dtype)
