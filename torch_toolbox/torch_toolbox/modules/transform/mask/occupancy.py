from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any

import torch
from torch import Tensor

from .... import CFGS
from ... import MODELS
from ...definition import Composable_Config
from ...model.definition import Trainable_Model
from typing import NamedTuple

from .geometry.spec import Feature_Spec

"""occupancy 관점의 영역 정보. "그 좌표에 재료가 있는가" 만.

- fill, convex hull 없음. 관통 구멍은 비어 있는 셀이고 그 자체가 정보
- 극좌표 셀 크기는 `r dr dtheta` 라 polar occupancy 는 1/r 가중 면적. cartesian(실제 면적)과의
  비가 "재료가 중심에 몰렸나 바깥에 퍼졌나". 셀 면적으로 가중해 일치시키면 그 정보가 사라짐
- occupancy 는 boolean 이 아니라 분수. 바깥 셀은 폭이 픽셀보다 커서 얇은 구멍을 삼키는데,
  분수면 값이 떨어져 흔적이 남음
- 반경 격자 간격 1 px (`Polar_Raster` 와 같은 상수)
"""


class Region_Profile(NamedTuple):
    """theta 별 반경 프로파일.

    Attributes:
        r_outer:  (B, NT) float. theta 별 재료가 있는 최대 반경 (px). 없으면 0
        r_inner:  (B, NT) float. theta 별 재료가 있는 최소 반경 (px). 없으면 0.
            "중심에 재료 있음" 과 "재료 없음" 이 둘 다 0 -> `coverage` 로 구분
        coverage: (B, NT) float. theta 별 occupancy 평균 [0, 1]
    """

    r_outer:  Tensor
    r_inner:  Tensor
    coverage: Tensor


_OCCUPANCY_TOTALS_NAME = "occupancy_totals"
_OCCUPANCY_TOTALS_CFG  = f"{_OCCUPANCY_TOTALS_NAME}_Config"


@CFGS.Register_module(_OCCUPANCY_TOTALS_CFG)
@dataclass
class OccupancyTotals_Config(Composable_Config):
    """직교/극좌표 occupancy 총량 설정.

    Attributes:
        trust_radius: 샘플 반경 (px, 정수). r bin 수와 같음. Spec 상한 도출
        num_angular: theta bin 수
    """
    config_type: str = _OCCUPANCY_TOTALS_CFG
    object_type: str = _OCCUPANCY_TOTALS_NAME
    trainable: bool = False
    trust_radius: int = 224
    num_angular: int = 512


@MODELS.Register_module(_OCCUPANCY_TOTALS_NAME)
class Occupancy(Trainable_Model):
    """직교/극좌표 occupancy 총량 ``(area_cartesian_sqrt, area_polar_sqrt, area_ratio)``.

    - `area_cartesian_sqrt` : 전경 픽셀 합의 sqrt. 실제 면적에 비례
    - `area_polar_sqrt` : 극좌표 셀 occupancy 합의 sqrt. 1/r 가중
    - sqrt 인 이유 : 길이 차원이라야 도메인 나눗값 하나로 정규화. px^2 는 600x800 에서 FP16 을
      넘어 TRT 가 inf. `mean` 에서 곧장 sqrt 로 가 중간값도 안전
    """

    dim: int = 3

    def Out_channels(self) -> list[int]:
        return [self.dim]

    def Build(
        self, trust_radius: int = 224, num_angular: int = 512, **kwargs: Any,
    ) -> None:
        self.trust_radius = int(trust_radius)
        self.cells = self.trust_radius * int(num_angular)

    def Spec(self) -> tuple[Feature_Spec, ...]:
        """원본 스케일(선형). 형상 크기라 log 로 뭉개지 않음. 비는 실용 상한."""
        _disk_sqrt = math.sqrt(math.pi) * self.trust_radius
        return (
            Feature_Spec("area_cartesian_sqrt", 1, "identity", (0.0, _disk_sqrt)),
            Feature_Spec("area_polar_sqrt",     1, "identity", (0.0, math.sqrt(self.cells))),
            Feature_Spec("area_ratio",          1, "identity", (0.0, 20.0)),
        )

    def forward(self, mask: Tensor, polar: Tensor) -> Tensor:
        """
        Args:
            mask:  (B, 1, H, W) float. 전경 1, 배경 0.
            polar: (B, NR, NT) float. `Polar_Raster` 출력.

        Returns:
            (B, 3) float. `area_cartesian_sqrt`, `area_polar_sqrt`, 그 비(면적 기준).
        """
        _h, _w = mask.shape[-2], mask.shape[-1]
        _cart = mask.mean(dim=(1, 2, 3)).clamp_min(0).sqrt() * ((_h * _w) ** 0.5)
        _pol = polar.mean(dim=(1, 2)).clamp_min(0).sqrt() * (self.cells ** 0.5)
        _r = _pol / _cart.clamp_min(1e-4)
        return torch.stack([_cart, _pol, _r * _r], dim=1)


_RADIAL_PROFILE_NAME = "radial_profile"
_RADIAL_PROFILE_CFG  = f"{_RADIAL_PROFILE_NAME}_Config"


@CFGS.Register_module(_RADIAL_PROFILE_CFG)
@dataclass
class RadialProfile_Config(Composable_Config):
    """theta 별 반경 프로파일 설정.

    Attributes:
        threshold: 셀을 "재료 있음" 으로 볼 occupancy 분수 하한
    """
    config_type: str = _RADIAL_PROFILE_CFG
    object_type: str = _RADIAL_PROFILE_NAME
    trainable: bool = False
    threshold: float = 0.5


@MODELS.Register_module(_RADIAL_PROFILE_NAME)
class Radial_Profile(Trainable_Model):
    """극좌표 occupancy -> theta 별 ``(r_outer, r_inner, coverage)``.

    빈 bin 은 0. "이 방향엔 재료가 없다" 는 사실이라 보간으로 지어내지 않음.
    """

    def Out_channels(self) -> list[int]:
        """r_outer / r_inner / coverage 세 텐서."""
        return [1, 1, 1]

    def Build(self, threshold: float = 0.5, **kwargs: Any) -> None:
        self.dr = 1.0
        self.threshold = float(threshold)

    def forward(self, polar: Tensor) -> Region_Profile:
        """
        Args:
            polar: (B, NR, NT) float. occupancy 분수.

        Returns:
            :class:`Region_Profile`.
        """
        _nr = polar.shape[1]
        _idx = torch.arange(_nr, device=polar.device, dtype=polar.dtype).view(1, -1, 1)
        _hit = polar >= self.threshold                                   # (B, NR, NT)

        # 재료 없는 셀은 max 에서 -1, min 에서 NR 로 밀어 극단값이 안 잡히게
        _outer = torch.where(_hit, _idx, torch.full_like(_idx, -1.0)).amax(dim=1)
        _inner = torch.where(_hit, _idx, torch.full_like(_idx, float(_nr))).amin(dim=1)
        _has = _outer >= 0.0                                             # (B, NT)

        _zero = torch.zeros_like(_outer)
        return Region_Profile(
            r_outer=torch.where(_has, (_outer + 0.5) * self.dr, _zero),
            r_inner=torch.where(_has, (_inner + 0.5) * self.dr, _zero),
            coverage=polar.mean(dim=1),
        )


_RADIAL_RLE_NAME = "radial_rle"
_RADIAL_RLE_CFG  = f"{_RADIAL_RLE_NAME}_Config"


@CFGS.Register_module(_RADIAL_RLE_CFG)
@dataclass
class RadialRLE_Config(Composable_Config):
    """theta 별 재료 RLE 설정.

    Attributes:
        threshold: 셀을 "재료 있음" 으로 볼 occupancy 분수 하한
        max_transitions: theta 당 슬롯 수 `K`. 넘는 전이는 잘림. 출력 차원 = K
    """
    config_type: str = _RADIAL_RLE_CFG
    object_type: str = _RADIAL_RLE_NAME
    trainable: bool = False
    threshold: float = 0.5
    max_transitions: int = 8


@MODELS.Register_module(_RADIAL_RLE_NAME)
class Radial_RLE(Trainable_Model):
    """극좌표 occupancy -> theta 별 재료 RLE 간격 ``(B, NT, K)``.

    슬롯 = ``[시작 반경, 살1, 구멍1, 살2, 구멍2, ...]`` (안쪽부터, px). 빈 자리 0.
    전이점(절대 반경)이 아니라 간격인 이유 : 슬롯 의미가 고정이라 밴드 수가 달라도 위치별
    평균이 성립. 전이점이면 밴드 없는 형상에서 슬롯이 밀려 class 평균이 무너짐.
    """

    def Out_channels(self) -> list[int]:
        """간격 한 텐서. `K` 채널."""
        return [self.max_transitions]

    def Build(self, threshold: float = 0.5, max_transitions: int = 8, **kwargs: Any) -> None:
        self.dr = 1.0
        self.threshold = float(threshold)
        self.max_transitions = int(max_transitions)

    def forward(self, polar: Tensor) -> Tensor:
        """
        Args:
            polar: (B, NR, NT) float. occupancy 분수.

        Returns:
            (B, NT, K) float. theta 당 간격 (px). 빈 자리 0.
        """
        _b, _nr, _nt = polar.shape
        _hit = (polar >= self.threshold).to(polar.dtype)                 # (B, NR, NT)

        # r 축 인접 차분 절댓값 = 모든 전이 (0->1, 1->0). r=0 앞, r=NR 뒤 0 패딩
        _pad = torch.zeros(_b, 1, _nt, dtype=polar.dtype, device=polar.device)
        _h = torch.cat([_pad, _hit, _pad], dim=1)                        # (B, NR+2, NT)
        _trans = (_h[:, 1:] - _h[:, :-1]).abs() > 0.5                    # (B, NR+1, NT)
        _ridx = torch.arange(_nr + 1, device=polar.device, dtype=polar.dtype).view(1, -1, 1)

        _K = self.max_transitions
        _rank = torch.cumsum(_trans.to(torch.int64), dim=1)             # 전이 누적 순번
        _tr = torch.zeros(_b, _nt, _K, dtype=polar.dtype, device=polar.device)
        _cnt = _rank[:, -1, :]                                           # (B, NT) theta 당 전이 수
        for _k in range(_K):
            _sel = _trans & (_rank == (_k + 1))
            _tr[:, :, _k] = (_ridx * _sel.to(_ridx.dtype)).sum(dim=1) * self.dr

        # 간격 [t0, t1-t0, t2-t1, ...]. 존재하는 전이까지만, 뒤 슬롯은 0
        _out = torch.zeros_like(_tr)
        _out[:, :, 0] = _tr[:, :, 0]
        for _k in range(1, _K):
            _gap = _tr[:, :, _k] - _tr[:, :, _k - 1]
            _valid = (_cnt >= (_k + 1))
            _out[:, :, _k] = torch.where(_valid, _gap, torch.zeros_like(_gap))
        return _out
