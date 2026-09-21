from __future__ import annotations
from typing import NamedTuple

import torch
from torch import Tensor

"""극좌표 occupancy 측정. 입력은 `Radial` 출력 ``(B, NR, NT)``. "그 좌표에 재료가 있는가" 만.

- fill, convex hull 없음. 관통 구멍은 비어 있는 셀이고 그 자체가 정보
- 반경 격자 간격 1 u. 반경 출력은 u
- occupancy 는 boolean 이 아니라 분수. 바깥 셀은 폭이 픽셀보다 커서 얇은 구멍을 삼키는데,
  분수면 값이 떨어져 흔적이 남음
"""


class Region_Profile(NamedTuple):
    """theta 별 반경 프로파일.

    Attributes:
        r_outer:  (B, NT) float. theta 별 재료가 있는 최대 반경 (u). 없으면 0
        r_inner:  (B, NT) float. theta 별 재료가 있는 최소 반경 (u). 없으면 0.
            "중심에 재료 있음" 과 "재료 없음" 이 둘 다 0 -> `coverage` 로 구분
        coverage: (B, NT) float. theta 별 occupancy 평균 [0, 1]
    """

    r_outer:  Tensor
    r_inner:  Tensor
    coverage: Tensor


def Occupancy_totals(mask: Tensor, polar: Tensor, *, px_size: float) -> Tensor:
    """직교/극좌표 occupancy 총량.

    - `area_cartesian_sqrt` : 전경 픽셀 합의 sqrt. 실제 면적에 비례
    - `area_polar_sqrt` : 극좌표 셀 occupancy 합의 sqrt. 셀 크기가 `r dr dtheta` 라 1/r 가중
    - 비 = "재료가 중심에 몰렸나 바깥에 퍼졌나". 셀 면적으로 가중해 일치시키면 이 정보가 사라짐
    - sqrt : 길이 차원이라야 나눗값 하나로 정규화. px^2 는 600x800 에서 FP16 을 넘어 TRT 가 inf.
      `mean` 에서 곧장 sqrt 로 가 중간값도 안전

    Args:
        mask: (B, 1, H, W) float. 전경 1, 배경 0.
        polar: (B, NR, NT) float. `Radial` 출력.
        px_size: 입력 1 px 의 길이 / u. `Radial` 과 같은 값.

    Returns:
        (B, 3) float. [area_cartesian_sqrt (u), area_polar_sqrt (셀), 그 비의 제곱 (면적 기준)].
    """
    _h, _w = mask.shape[-2], mask.shape[-1]
    _cells = polar.shape[1] * polar.shape[2]
    _cart = mask.mean(dim=(1, 2, 3)).clamp_min(0).sqrt() * ((_h * _w) ** 0.5) * px_size
    _pol = polar.mean(dim=(1, 2)).clamp_min(0).sqrt() * (_cells ** 0.5)
    _r = _pol / _cart.clamp_min(1e-4)
    return torch.stack([_cart, _pol, _r * _r], dim=1)


def Radial_profile(polar: Tensor, *, threshold: float) -> Region_Profile:
    """theta 별 ``(r_outer, r_inner, coverage)``.

    빈 bin 은 0. "이 방향엔 재료가 없다" 는 사실이라 보간으로 지어내지 않음.

    Args:
        polar: (B, NR, NT) float. occupancy 분수.
        threshold: 셀을 "재료 있음" 으로 볼 occupancy 분수 하한.

    Returns:
        :class:`Region_Profile`.
    """
    _nr = polar.shape[1]
    _idx = torch.arange(_nr, device=polar.device, dtype=polar.dtype).view(1, -1, 1)
    _hit = polar >= threshold                                        # (B, NR, NT)

    # 재료 없는 셀은 max 에서 -1, min 에서 NR 로 밀어 극단값이 안 잡히게
    _outer = torch.where(_hit, _idx, torch.full_like(_idx, -1.0)).amax(dim=1)
    _inner = torch.where(_hit, _idx, torch.full_like(_idx, float(_nr))).amin(dim=1)
    _has = _outer >= 0.0                                             # (B, NT)

    _zero = torch.zeros_like(_outer)
    return Region_Profile(
        r_outer=torch.where(_has, _outer + 0.5, _zero),
        r_inner=torch.where(_has, _inner + 0.5, _zero),
        coverage=polar.mean(dim=1),
    )


def Radial_rle(polar: Tensor, *, threshold: float, max_transitions: int) -> Tensor:
    """theta 별 재료 RLE 간격.

    슬롯 = ``[시작 반경, 살1, 구멍1, 살2, 구멍2, ...]`` (안쪽부터, u). 빈 자리 0.
    전이점(절대 반경)이 아니라 간격인 이유 : 슬롯 의미가 고정이라 밴드 수가 달라도 위치별
    평균이 성립. 전이점이면 밴드 없는 형상에서 슬롯이 밀려 class 평균이 무너짐.

    Args:
        polar: (B, NR, NT) float. occupancy 분수.
        threshold: 셀을 "재료 있음" 으로 볼 occupancy 분수 하한.
        max_transitions: theta 당 슬롯 수 `K`. 넘는 전이는 잘림.

    Returns:
        (B, NT, K) float. theta 당 간격 (u). 빈 자리 0.
    """
    _b, _nr, _nt = polar.shape
    _hit = (polar >= threshold).to(polar.dtype)                      # (B, NR, NT)

    # r 축 인접 차분 절댓값 = 모든 전이 (0->1, 1->0). r=0 앞, r=NR 뒤 0 패딩
    _pad = torch.zeros(_b, 1, _nt, dtype=polar.dtype, device=polar.device)
    _h = torch.cat([_pad, _hit, _pad], dim=1)                        # (B, NR+2, NT)
    _trans = (_h[:, 1:] - _h[:, :-1]).abs() > 0.5                    # (B, NR+1, NT)
    _ridx = torch.arange(_nr + 1, device=polar.device, dtype=polar.dtype).view(1, -1, 1)

    _K = max_transitions
    _rank = torch.cumsum(_trans.to(torch.int64), dim=1)             # 전이 누적 순번
    _tr = torch.zeros(_b, _nt, _K, dtype=polar.dtype, device=polar.device)
    _cnt = _rank[:, -1, :]                                           # (B, NT) theta 당 전이 수
    for _k in range(_K):
        _sel = _trans & (_rank == (_k + 1))
        _tr[:, :, _k] = (_ridx * _sel.to(_ridx.dtype)).sum(dim=1)

    # 간격 [t0, t1-t0, t2-t1, ...]. 존재하는 전이까지만, 뒤 슬롯은 0
    _out = torch.zeros_like(_tr)
    _out[:, :, 0] = _tr[:, :, 0]
    for _k in range(1, _K):
        _gap = _tr[:, :, _k] - _tr[:, :, _k - 1]
        _out[:, :, _k] = torch.where(_cnt >= (_k + 1), _gap, torch.zeros_like(_gap))
    return _out


def Rle_signed(rle: Tensor) -> Tensor:
    """RLE 간격 -> 부호합 = 살합 - 빈공간합. 구멍 총량이 같으면 같음.

    짝수 슬롯이 빈 공간, 홀수가 살. 광선이 구멍을 스칠 때 rle 는 슬롯이 밀려 계단으로 뛰지만
    부호합은 연속.

    Args:
        rle: (B, NT, K). `Radial_rle` 출력.

    Returns:
        (B, NT).
    """
    _sign = torch.where(torch.arange(rle.shape[-1], device=rle.device) % 2 == 1, 1.0, -1.0)
    return (rle * _sign).sum(-1)


def Rle_outline(rle: Tensor) -> Tensor:
    """RLE 간격 -> 마지막 전이 반경. 실루엣만 같으면 같음.

    Args:
        rle: (B, NT, K). `Radial_rle` 출력.

    Returns:
        (B, NT).
    """
    return rle.sum(-1)
