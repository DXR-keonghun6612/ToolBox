from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any

import torch
from torch import Tensor

from ... import CFGS
from .. import MODELS
from ..definition import Composable_Config
from ..model.definition import Trainable_Model

from .functional.frame import Frame
from .functional.sample import Gather_points

"""직교 -> 극좌표 샘플링 layer. state = 오프셋 LUT. 측정은 `functional.polar`."""


_NAME = "radial"
_CFG  = f"{_NAME}_Config"


@CFGS.Register_module(_CFG)
@dataclass
class Radial_Config(Composable_Config):
    """극좌표 샘플링 설정.

    Attributes:
        trust_radius: 샘플 반경 (도메인 단위 u, 정수). 이 안은 1 u 간격으로 전부 읽고 밖은 안 읽음.
            r bin 수 `NR` 와 같음
        num_angular: theta bin 수 `NT`
        sub_per_px: 입력 1 px 당 축별 표본 수. 셀당 축별 표본은 `ceil(sub_per_px / px_size)`,
            셀당 표본 그 제곱
        px_size: 입력 1 px 의 길이 / u. 입력을 리샘플하지 않고 샘플 간격으로 반영. 상한 1
    """
    config_type: str = _CFG
    object_type: str = _NAME
    trainable: bool = False
    trust_radius: int = 224
    num_angular: int = 512
    sub_per_px: int = 1
    px_size: float = 1.0


@MODELS.Register_module(_NAME)
class Radial(Trainable_Model):
    """이진 마스크 + :class:`Frame` -> ``(B, NR, NT)`` occupancy 분수. backward gather.

    - 셀마다 자기 좌표에서 마스크를 읽음. forward scatter(픽셀 -> 셀)는 안쪽에서 빈 셀이 가짜
      구멍이 되고 바깥쪽에서 여러 픽셀이 뭉쳐 진짜 구멍이 흡수됨 (실측 : 224 캔버스에서 안쪽 빈 셀 51%)
    - occupancy 는 boolean 이 아니라 면적 분수. 바깥쪽 흡수를 분수 하락으로 남김. `sub_per_px` 가
      손잡이, 늘려도 연산 종류는 그대로고 상수 테이블만 커짐
    - 원점이 정수(`Frame.origin`)라 샘플 위치 소수부가 상수 -> bilinear 가중치 상수,
      정수 인덱스만 원점만큼 이동. `GridSample` 없이 `Gather`/`Mul`/`Add`
    - 회전은 theta 축 circular roll. 출력 theta 는 주축 정렬 완료
    - 반경 격자는 1 u 간격 (입력 `1 / px_size` px), `trust_radius` 까지. 캔버스 크기는 값에 안 남음
    - 표본 간격은 입력 px 기준 `1 / sub_per_px` 고정. 격자가 바뀌어도 px 당 밀도 불변
      -> occupancy 분포와 `threshold` 의미 보존
    - LUT 버퍼는 `persistent=False` 라 state_dict 에 없으나 ONNX 에는 initializer 로 구워짐.
      `trust_radius`/`NT`/`sub_per_px`/`px_size` 변경 = 재export. 런타임 메모리는
      `B * NR * NT * sub^2` 에 비례
    """

    _base_col: Tensor
    _base_row: Tensor
    _frac_x: Tensor
    _frac_y: Tensor
    _theta_idx: Tensor

    def Out_channels(self) -> list[int]:
        """occupancy 격자 하나. 채널 축이 없으므로 r bin 수."""
        return [self.num_radial]

    def Build(
        self,
        trust_radius: int = 224,
        num_angular: int = 512,
        sub_per_px: int = 1,
        px_size: float = 1.0,
        **kwargs: Any,
    ) -> None:
        if trust_radius <= 0:
            raise ValueError(f"trust_radius 는 양수: {trust_radius}")
        if not 0.0 < px_size <= 1.0:
            raise ValueError(
                f"px_size 는 (0, 1]: {px_size}. 입력 격자가 u 보다 거침 - 반경 격자가 더 촘촘해져 "
                f"occupancy 가 면적 분수가 아니라 보간값")
        if sub_per_px < 1:
            raise ValueError(f"sub_per_px 는 1 이상: {sub_per_px}")
        self.num_radial = int(trust_radius)
        self.num_angular = int(num_angular)
        self.px_size = float(px_size)
        self.sub = math.ceil(int(sub_per_px) / self.px_size)
        self.dtheta = 2.0 * math.pi / self.num_angular

        # 셀 중심 정렬 + 셀 내부 sub x sub 격자. 반경 간격 1 u = 입력 1 / px_size px
        _i = torch.arange(self.num_radial, dtype=torch.float64)
        _j = torch.arange(self.num_angular, dtype=torch.float64)
        _a = (torch.arange(self.sub, dtype=torch.float64) + 0.5) / self.sub
        _r = (_i.view(-1, 1, 1, 1) + _a.view(1, 1, -1, 1)) / self.px_size
        _t = (_j.view(1, -1, 1, 1) + _a.view(1, 1, 1, -1)) * self.dtheta - math.pi

        _ox = _r * torch.cos(_t)                       # (NR, NT, sub, sub) 원점 기준 오프셋
        _oy = _r * torch.sin(_t)
        _c0 = torch.floor(_ox)
        _r0 = torch.floor(_oy)

        self.register_buffer("_base_col", _c0.reshape(-1).to(torch.int32), persistent=False)
        self.register_buffer("_base_row", _r0.reshape(-1).to(torch.int32), persistent=False)
        self.register_buffer("_frac_x", (_ox - _c0).reshape(-1).to(torch.float32), persistent=False)
        self.register_buffer("_frac_y", (_oy - _r0).reshape(-1).to(torch.float32), persistent=False)
        self.register_buffer("_theta_idx", torch.arange(self.num_angular), persistent=False)

    def forward(self, mask: Tensor, frame: Frame) -> Tensor:
        """
        Args:
            mask: (B, 1, H, W) float. 전경 1, 배경 0.
            frame: :class:`Frame`. `origin` 과 `angle` 을 씀.

        Returns:
            (B, NR, NT) float. 셀별 occupancy 분수 [0, 1]. theta 는 주축 정렬 완료.
        """
        _b = mask.shape[0]
        _h, _w = mask.shape[-2], mask.shape[-1]
        _flat = mask.reshape(_b, -1)

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
        _val = _val.view(_b, self.num_radial, self.num_angular, self.sub * self.sub).mean(dim=3)

        _roll = torch.round(frame.angle / self.dtheta).long().view(-1, 1)   # (B, 1)
        _jdx = (self._theta_idx.view(1, -1) + _roll) % self.num_angular     # (B, NT)
        _jdx = _jdx.unsqueeze(1).expand(-1, self.num_radial, -1)
        return _val.gather(2, _jdx)
