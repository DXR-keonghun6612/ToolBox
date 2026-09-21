"""정렬 좌표 `(u, v)` (`Frame_coords`, 무차원, 원점 centroid) 측정. 리덕션과 닫힌 해로만. 길이 출력은 u."""
from __future__ import annotations
import math

import torch
from torch import Tensor
from torch.nn import functional as F


# 면적 항은 sqrt (길이 차원)
SIZE_NAMES  = ("area_sqrt", "perimeter", "major", "minor", "bbox_u", "bbox_v",
               "area_swept_sqrt")
RATIO_NAMES = ("bbox_aspect", "axis_ratio", "extent", "fill_ratio", "circularity")
POS_NAMES   = ("centroid_du", "centroid_dv")

_AREA_EPS = 1e-4         #: 전경 화소 비율 하한
_DIV_EPS = 1e-12         #: 비율 분모 하한


def _Safe_div(a: Tensor, b: Tensor) -> Tensor:
    """0 나눗셈은 0."""
    return torch.where(b.abs() > _DIV_EPS, a / b.clamp_min(_DIV_EPS), torch.zeros_like(a))


def Region_scalars(
    mask: Tensor, u: Tensor, v: Tensor, r_outer: Tensor, *, trust_radius: int, px_size: float,
) -> Tensor:
    """크기 7 + 비율 5 + 위치 2 스칼라. 전부 u 또는 무차원 비.

    - `area_swept` = 반경 프로파일 적분 `0.5 r_outer^2 dtheta` (convex hull 대용). `fill_ratio = area / area_swept`
    - 둘레 = morphological gradient (dilate - erode) 전경 화소 수 x `px_size`. 구멍 둘레 포함
    - major / minor 는 분산 크기순

    Args:
        mask: (B, 1, H, W) float.
        u, v: (B, H, W) float. `Frame_coords` 출력.
        r_outer: (B, NT) float. `Radial_profile` 의 `r_outer` (u).
        trust_radius: `Frame_coords` 와 같은 값. 나눈 것을 되곱함.
        px_size: 입력 1 px 의 길이 / u. `Frame_coords` 와 같은 값.

    Returns:
        (B, 14) float. `SIZE_NAMES` + `RATIO_NAMES` + `POS_NAMES` 순.
    """
    _norm = float(trust_radius)
    _m = mask[:, 0]
    _h, _w = mask.shape[-2], mask.shape[-1]

    _nm = _m.mean(dim=(1, 2)).clamp_min(_AREA_EPS)         # (B,) 전경 화소 비율
    _area_sqrt = _nm.sqrt() * ((_h * _w) ** 0.5) * px_size  # (B,) u

    _dil = F.max_pool2d(mask, 3, stride=1, padding=1)
    _ero = -F.max_pool2d(-mask, 3, stride=1, padding=1)
    _perimeter = (_dil - _ero).sum(dim=(1, 2, 3)) * px_size

    # 주축 정렬 bbox
    _big = torch.full_like(u, 1e9)
    _hit = _m > 0
    _umin = torch.where(_hit, u, _big).amin(dim=(1, 2))
    _umax = torch.where(_hit, u, -_big).amax(dim=(1, 2))
    _vmin = torch.where(_hit, v, _big).amin(dim=(1, 2))
    _vmax = torch.where(_hit, v, -_big).amax(dim=(1, 2))
    _bu = (_umax - _umin) * _norm
    _bv = (_vmax - _vmin) * _norm

    _lu = (_m * u * u).mean(dim=(1, 2)) / _nm
    _lv = (_m * v * v).mean(dim=(1, 2)) / _nm
    _major = 4.0 * torch.maximum(_lu, _lv).clamp_min(0).sqrt() * _norm
    _minor = 4.0 * torch.minimum(_lu, _lv).clamp_min(0).sqrt() * _norm

    # Sum(.) dtheta = mean(.) 2pi
    _ro = r_outer / _norm
    _swept_sqrt = (math.pi * (_ro * _ro).mean(dim=1)).clamp_min(0).sqrt() * _norm

    _size = torch.stack(
        [_area_sqrt, _perimeter, _major, _minor, _bu, _bv, _swept_sqrt], dim=1)
    # 비율은 sqrt 끼리 나눔. extent = (a/bu)(a/bv), fill = (a/s)^2, circularity = 4pi (a/p)^2
    _fill = _Safe_div(_area_sqrt, _swept_sqrt)
    _circ = _Safe_div(_area_sqrt, _perimeter)
    _ratio = torch.stack(
        [
            _Safe_div(_bu, _bv),
            _Safe_div(_major, _minor),
            _Safe_div(_area_sqrt, _bu) * _Safe_div(_area_sqrt, _bv),
            _fill * _fill,
            4.0 * math.pi * _circ * _circ,
        ],
        dim=1,
    )
    # bbox 중심 오프셋 (원점 = centroid)
    _pos = torch.stack(
        [-(_umax + _umin) / 2.0 * _norm, -(_vmax + _vmin) / 2.0 * _norm], dim=1)
    return torch.cat([_size, _ratio, _pos], dim=1)


def Chirality_moments(mask: Tensor, u: Tensor, v: Tensor) -> Tensor:
    """정렬 좌표 좌우 / 상하 불균형 (전경 비율) + 3차 중심 모멘트 (무차원). 거울상에서 부호 반전.

    Args:
        mask: (B, 1, H, W) float. 전경 1, 배경 0.
        u, v: (B, H, W) float. `Frame_coords` 출력.

    Returns:
        (B, 6) float. [chirality_lr, chirality_ud, mu30, mu03, mu21, mu12]. 전부 [-1, 1] 근처 유계.
    """
    _m = mask[:, 0]
    _n = _m.sum(dim=(1, 2)).clamp_min(1.0)

    _lr = (_m * torch.where(u >= 0, 1.0, -1.0)).sum(dim=(1, 2)) / _n
    _ud = (_m * torch.where(v >= 0, 1.0, -1.0)).sum(dim=(1, 2)) / _n

    _mu30 = (_m * u * u * u).sum(dim=(1, 2)) / _n
    _mu03 = (_m * v * v * v).sum(dim=(1, 2)) / _n
    _mu21 = (_m * u * u * v).sum(dim=(1, 2)) / _n
    _mu12 = (_m * u * v * v).sum(dim=(1, 2)) / _n
    return torch.stack([_lr, _ud, _mu30, _mu03, _mu21, _mu12], dim=1)
