"""직교 -> 극좌표 샘플링 layer. state = 오프셋 LUT, 스무딩 커널. 측정은 `functional.polar`."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor

from ... import CFGS
from .. import MODELS
from ..definition import Composable_Config
from ..model.definition import Trainable_Model

from .functional.frame import Frame
from .functional.sample import Gather_points


_NAME = "radial"
_CFG  = f"{_NAME}_Config"

#: 마스크 스무딩 가우시안 표준편차 (입력 px). 커널 한 변 `2 * ceil(3 sigma) + 1`
_SMOOTH_SIGMA = 2.0


@CFGS.Register_module(_CFG)
@dataclass
class Radial_Config(Composable_Config):
    """극좌표 샘플링 설정.

    Attributes:
        trust_radius: 샘플 반경 (도메인 단위 u, 정수). 이 안은 1 u 간격으로 전부 읽고 밖은 안 읽음.
            r bin 수 `NR` 와 같음
        num_angular: theta bin 수 `NT`
        px_size: 입력 1 px 의 길이 / u. 입력을 리샘플하지 않고 샘플 간격으로 반영. 상한 1
    """
    config_type: str = _CFG
    object_type: str = _NAME
    trainable: bool = False
    trust_radius: int = 224
    num_angular: int = 512
    px_size: float = 1.0


@MODELS.Register_module(_NAME)
class Radial(Trainable_Model):
    """이진 마스크 + `Frame` -> `(B, NR, NT)` occupancy. backward gather.

    - 마스크를 가우시안 (`_SMOOTH_SIGMA` px) 으로 스무딩한 뒤 읽음. 이진 그대로면 벽을 스치는 반경선에서
      값이 0.5 를 오가 `Radial_rle` 전이가 수십 개로 늚
    - 셀마다 중심 한 점에서 둘레 4 화소를 거리 가중 (bilinear). 표본 수 없음 - 저역은 스무딩 몫
    - 원점이 정수 (`Frame.origin`) 라 소수부, bilinear 가중치는 LUT 상수. 정수 인덱스만 원점만큼 이동.
      `Conv` / `Gather` / `Mul` / `Add` 만
    - 회전은 theta 축 circular roll. 출력 theta 는 주축 정렬 완료
    - 반경 격자는 1 u 간격 (입력 `1 / px_size` px), `trust_radius` 까지
    - LUT 버퍼는 `persistent=False`. ONNX 에는 initializer. Config 값 변경 = 재export.
      메모리 `B * NR * NT`
    """

    _base_col: Tensor
    _base_row: Tensor
    _frac_x: Tensor
    _frac_y: Tensor
    _theta_idx: Tensor
    _smooth: Tensor

    def Out_channels(self) -> list[int]:
        """`[NR]`. 채널 축 없음."""
        return [self.num_radial]

    def Build(
        self,
        trust_radius: int = 224,
        num_angular: int = 512,
        px_size: float = 1.0,
        **kwargs: Any,
    ) -> None:
        if trust_radius <= 0:
            raise ValueError(f"trust_radius 는 양수: {trust_radius}")
        if not 0.0 < px_size <= 1.0:
            raise ValueError(
                f"px_size 는 (0, 1]: {px_size}. 입력 격자가 u 보다 거침 - 반경 격자가 입력보다 촘촘해짐")
        self.num_radial = int(trust_radius)
        self.num_angular = int(num_angular)
        self.px_size = float(px_size)
        self.dtheta = 2.0 * math.pi / self.num_angular

        # 셀 중심. 반경 간격 1 u = 입력 1 / px_size px
        _i = torch.arange(self.num_radial, dtype=torch.float64)
        _j = torch.arange(self.num_angular, dtype=torch.float64)
        _r = (_i.view(-1, 1) + 0.5) / self.px_size
        _t = (_j.view(1, -1) + 0.5) * self.dtheta - math.pi

        _ox = _r * torch.cos(_t)                       # (NR, NT) 원점 기준 오프셋
        _oy = _r * torch.sin(_t)
        _c0 = torch.floor(_ox)
        _r0 = torch.floor(_oy)

        _half = math.ceil(3.0 * _SMOOTH_SIGMA)
        _a = torch.arange(-_half, _half + 1, dtype=torch.float64)
        _g = torch.exp(-_a * _a / (2.0 * _SMOOTH_SIGMA ** 2))

        self.register_buffer("_base_col", _c0.reshape(-1).to(torch.int32), persistent=False)
        self.register_buffer("_base_row", _r0.reshape(-1).to(torch.int32), persistent=False)
        self.register_buffer("_frac_x", (_ox - _c0).reshape(-1).to(torch.float32), persistent=False)
        self.register_buffer("_frac_y", (_oy - _r0).reshape(-1).to(torch.float32), persistent=False)
        self.register_buffer("_theta_idx", torch.arange(self.num_angular), persistent=False)
        self.register_buffer("_smooth", (_g / _g.sum()).to(torch.float32), persistent=False)

    def forward(self, mask: Tensor, frame: Frame) -> Tensor:
        """
        Args:
            mask: (B, 1, H, W) float. 전경 1, 배경 0.
            frame: `origin` 과 `angle` 사용.

        Returns:
            (B, NR, NT) float. 셀 중심의 스무딩한 마스크 값 [0, 1]. theta 는 주축 정렬 완료.
        """
        _b = mask.shape[0]
        _h, _w = mask.shape[-2], mask.shape[-1]

        # 분리 가우시안. 캔버스 밖은 배경 (0 패딩)
        _k = self._smooth.to(mask)
        _p = _k.shape[0] // 2
        _soft = F.conv2d(mask, _k.view(1, 1, 1, -1), padding=(0, _p))
        _soft = F.conv2d(_soft, _k.view(1, 1, -1, 1), padding=(_p, 0))
        _flat = _soft.reshape(_b, -1)

        _c0 = self._base_col.view(1, -1).long() + frame.origin[:, 0].view(-1, 1)    # (B, P)
        _r0 = self._base_row.view(1, -1).long() + frame.origin[:, 1].view(-1, 1)
        _fx = self._frac_x.view(1, -1)
        _fy = self._frac_y.view(1, -1)

        _val = (
            Gather_points(_flat, _r0,     _c0,     _h, _w) * ((1.0 - _fy) * (1.0 - _fx))
            + Gather_points(_flat, _r0,     _c0 + 1, _h, _w) * ((1.0 - _fy) * _fx)
            + Gather_points(_flat, _r0 + 1, _c0,     _h, _w) * (_fy * (1.0 - _fx))
            + Gather_points(_flat, _r0 + 1, _c0 + 1, _h, _w) * (_fy * _fx)
        )
        _val = _val.view(_b, self.num_radial, self.num_angular)

        _roll = torch.round(frame.angle / self.dtheta).long().view(-1, 1)   # (B, 1)
        _jdx = (self._theta_idx.view(1, -1) + _roll) % self.num_angular     # (B, NT)
        _jdx = _jdx.unsqueeze(1).expand(-1, self.num_radial, -1)
        return _val.gather(2, _jdx)
