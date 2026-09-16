from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any

import torch
from torch import Tensor
from torch.nn import functional as F

from ..... import CFGS
from .... import MODELS
from ....definition import Composable_Config
from ....model.definition import Trainable_Model

from .spec import Feature_Spec
from ..occupancy import Region_Profile

"""크기, 비율, 위치 스칼라. skimage `regionprops` 없이 리덕션과 닫힌 해로만.

- convex hull 은 ONNX 표현 불가 -> `area_swept` (radial profile 반음적분 `0.5 r_outer^2 dtheta`)
  와 `fill_ratio = area / area_swept`. 의미역이 같고 구멍에 민감
- 둘레 = morphological gradient (dilate - erode) 의 전경 화소 수. skimage 와 값은 다르나
  자기일관적이고 구멍 둘레도 셈
- 측정은 `Frame_Coords` 의 정렬 좌표에서. raster 회전 없음
- FP16 : px^2 를 만들지 않음. 면적은 전경 비율에서 곧장 sqrt, 길이는 무차원 좌표로 재고 `norm` 을
  되곱함
"""

# 면적 항은 sqrt. 전부 길이 차원이어야 도메인 나눗값 하나로 정규화
SIZE_NAMES  = ("area_sqrt", "perimeter", "major", "minor", "bbox_u", "bbox_v",
               "area_swept_sqrt")
RATIO_NAMES = ("bbox_aspect", "axis_ratio", "extent", "fill_ratio", "circularity")
POS_NAMES   = ("centroid_du", "centroid_dv")


def _safe_div(a: Tensor, b: Tensor) -> Tensor:
    """0 나눗셈은 0."""
    return torch.where(b.abs() > 1e-12, a / b.clamp_min(1e-12), torch.zeros_like(a))


_REGION_SCALARS_NAME = "region_scalars"
_REGION_SCALARS_CFG  = f"{_REGION_SCALARS_NAME}_Config"


@CFGS.Register_module(_REGION_SCALARS_CFG)
@dataclass
class Region_Scalars_Config(Composable_Config):
    """크기, 비율, 위치 스칼라 설정.

    Attributes:
        trust_radius: 길이 단위 상수 (px). `Frame_Coords` 와 같은 값 - 그쪽이 나눈 것을 되곱함.
            Spec 상한 도출
        num_angular: theta bin 수
    """
    config_type: str = _REGION_SCALARS_CFG
    object_type: str = _REGION_SCALARS_NAME
    trainable: bool = False
    trust_radius: int = 224
    num_angular: int = 512


@MODELS.Register_module(_REGION_SCALARS_NAME)
class Region_Scalars(Trainable_Model):
    """크기 7 + 비율 5 + 위치 2 = 14차원 스칼라. 전부 px 또는 무차원 비."""

    dim: int = len(SIZE_NAMES) + len(RATIO_NAMES) + len(POS_NAMES)

    def Out_channels(self) -> list[int]:
        return [self.dim]

    def Build(self, trust_radius: int = 224, num_angular: int = 512, **kwargs: Any) -> None:
        self.trust_radius = int(trust_radius)
        if self.trust_radius <= 0:
            raise ValueError(f"trust_radius 는 양수: {trust_radius}")
        self.norm = float(self.trust_radius)
        self.dtheta = 2.0 * math.pi / int(num_angular)

    def Spec(self) -> tuple[Feature_Spec, ...]:
        """원본 스케일(선형). 형상 정보라 log 로 뭉개지 않음. 비율은 실용 상한 10."""
        _len_max = 4.0 * self.norm
        return (
            Feature_Spec("size",     len(SIZE_NAMES),  "identity", (0.0, _len_max)),
            Feature_Spec("ratio",    len(RATIO_NAMES), "identity", (0.0, 10.0)),
            Feature_Spec("position", len(POS_NAMES),   "identity", (-self.norm, self.norm)),
        )

    def forward(
        self, mask: Tensor, u: Tensor, v: Tensor, profile: Region_Profile
    ) -> Tensor:
        """
        Args:
            mask: (B, 1, H, W) float.
            u, v: (B, H, W) float. 정렬 좌표 (무차원).
            profile: :class:`Region_Profile`. `r_outer` 를 씀.

        Returns:
            (B, 14) float. :data:`SIZE_NAMES` + :data:`RATIO_NAMES` + :data:`POS_NAMES` 순.
        """
        _m = mask[:, 0]
        _h, _w = mask.shape[-2], mask.shape[-1]

        _nm = _m.mean(dim=(1, 2)).clamp_min(1e-4)              # (B,) 전경 화소 비율
        _hw = (_h * _w) ** 0.5
        _area_sqrt = _nm.sqrt() * _hw                          # (B,) px

        _dil = F.max_pool2d(mask, 3, stride=1, padding=1)
        _ero = -F.max_pool2d(-mask, 3, stride=1, padding=1)
        _perimeter = (_dil - _ero).sum(dim=(1, 2, 3))

        # u, v 가 주축 정렬이라 이것이 회전 bbox
        _big = torch.full_like(u, 1e9)
        _hit = _m > 0
        _umin = torch.where(_hit, u, _big).amin(dim=(1, 2))
        _umax = torch.where(_hit, u, -_big).amax(dim=(1, 2))
        _vmin = torch.where(_hit, v, _big).amin(dim=(1, 2))
        _vmax = torch.where(_hit, v, -_big).amax(dim=(1, 2))
        _bu = (_umax - _umin) * self.norm
        _bv = (_vmax - _vmin) * self.norm

        # major/minor 는 축 이름이 아니라 분산 크기순. 근정사각에서 주축각이 90도 튀어도 불변
        _lu = (_m * u * u).mean(dim=(1, 2)) / _nm
        _lv = (_m * v * v).mean(dim=(1, 2)) / _nm
        _major = 4.0 * torch.maximum(_lu, _lv).clamp_min(0).sqrt() * self.norm
        _minor = 4.0 * torch.minimum(_lu, _lv).clamp_min(0).sqrt() * self.norm

        # Sum(.) dtheta = mean(.) 2pi 라 theta bin 수가 사라짐
        _ro = profile.r_outer / self.norm
        _swept_sqrt = (math.pi * (_ro * _ro).mean(dim=1)).clamp_min(0).sqrt() * self.norm

        _size = torch.stack(
            [_area_sqrt, _perimeter, _major, _minor, _bu, _bv, _swept_sqrt], dim=1)
        # 비율은 sqrt 끼리 나눔. extent = (a/bu)(a/bv), fill = (a/s)^2, circularity = 4pi (a/p)^2
        _fill = _safe_div(_area_sqrt, _swept_sqrt)
        _circ = _safe_div(_area_sqrt, _perimeter)
        _ratio = torch.stack(
            [
                _safe_div(_bu, _bv),
                _safe_div(_major, _minor),
                _safe_div(_area_sqrt, _bu) * _safe_div(_area_sqrt, _bv),
                _fill * _fill,
                4.0 * math.pi * _circ * _circ,
            ],
            dim=1,
        )
        # centroid 가 원점이라 bbox 중심 오프셋이 곧 비대칭 신호
        _pos = torch.stack(
            [-(_umax + _umin) / 2.0 * self.norm, -(_vmax + _vmin) / 2.0 * self.norm], dim=1
        )
        return torch.cat([_size, _ratio, _pos], dim=1)
