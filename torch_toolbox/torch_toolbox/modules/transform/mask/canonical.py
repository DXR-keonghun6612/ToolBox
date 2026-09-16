from __future__ import annotations
from dataclasses import dataclass
from typing import Any, NamedTuple

import torch
from torch import Tensor

from .... import CFGS
from ... import MODELS
from ...definition import Composable_Config
from ...model.definition import Trainable_Model

"""정준 좌표계(frame) 산출. 파라미터만 냄. raster 회전 없음.

- 각도는 값으로만. 회전은 하류(`Polar_Raster`)가 theta 축 roll 로 소비
- 원점은 정수 양자화. 하류 bilinear 가중치가 상수가 되어 `GridSample` 없이 `Gather`/`Mul`/`Add` 로
  극좌표 리샘플. sub-pixel 원점이면 그 상수성이 깨짐
- 극좌표와 해석적 측정이 같은 원점(centroid)
- 길이 단위 상수 `trust_radius` 하나. 좌표를 그것으로 나눠 무차원으로 두고 리덕션은 mean.
  px 로 누산하면 FP16 최대(65504)를 넘어 TRT 가 0 을 냄 (실측 : 224 캔버스에서 Sum(m dx^2) 3.1e6)
- 캔버스 크기는 값에 안 남음. 격자를 입력 크기에서 만들고 `int()` 를 안 써 동적 축 export
"""


def _Abs2(re: Tensor, im: Tensor) -> Tensor:
    """|re + i im|. `torch.hypot` 은 ONNX exporter 에 디컴포지션이 없어 export 실패.
    `clamp_min` 은 0 에서 sqrt 기울기 무한대 방지 (회전대칭 형상에서 0 이 실제로 나옴)."""
    return (re * re + im * im).clamp_min(1e-24).sqrt()


def _Grid(h: int, w: int, device: torch.device) -> tuple[Tensor, Tensor]:
    """캔버스 기하중심 기준 픽셀 좌표 ``(dy (1,H,1), dx (1,1,W))``. 입력 크기에서 만듦."""
    _ys = torch.arange(h, dtype=torch.float32, device=device) - (h - 1) / 2.0
    _xs = torch.arange(w, dtype=torch.float32, device=device) - (w - 1) / 2.0
    return _ys.view(1, h, 1), _xs.view(1, 1, w)


class Frame(NamedTuple):
    """정준 좌표계 파라미터.

    `angle` 은 두 신뢰도와 한 벌. 둘 다 0 근처면 각도는 노이즈 -> 소비처는 회전 불변 거리로
    (`torch_toolbox.metric.functional.vector.circular`).

    복원 : `Sxx + Syy = 2 scale^2`, `|Z2| = anisotropy 2 scale^2`,
    `lambda_+- = scale^2 (1 +- anisotropy)` (주축/부축 분산, px^2).

    Attributes:
        center: (B, 2) float. centroid (cx, cy). 입력 캔버스 px, sub-pixel
        origin: (B, 2) long. 정수 양자화한 극좌표 원점 (col, row)
        angle:  (B,) float. 주축각 (rad). 180도 모호성 확정 완료
        scale:  (B,) float. 회전반경 sqrt((Sxx+Syy)/2), px. 회전 불변, 정규화 안 된 유일한 크기량
        anisotropy:  (B,) float [0, 1]. k=2 harmonic 상대 크기 = `angle` 의 신뢰도.
            0 이면 주축 없음 (원환, n >= 3 회전대칭)
        flip_margin: (B,) float [0, 1]. k=3 harmonic 상대 크기 |Z3| / sum m r^3 = 180도 확정의
            신뢰도. 2회 회전대칭에서 0. `scale` 로 3차 모멘트를 복원할 수는 없음
    """

    center: Tensor
    origin: Tensor
    angle:  Tensor
    scale:  Tensor
    anisotropy:  Tensor
    flip_margin: Tensor


_FRAME_NAME = "centroid_frame"
_FRAME_CFG  = f"{_FRAME_NAME}_Config"
_COORD_NAME = "frame_coords"
_COORD_CFG  = f"{_COORD_NAME}_Config"


@CFGS.Register_module(_FRAME_CFG)
@dataclass
class Centroid_Frame_Config(Composable_Config):
    """정준 좌표계 산출 설정.

    Attributes:
        trust_radius: 길이 단위 상수 (px). 좌표 무차원화 `norm`. 입력 캔버스와 무관.
            실루엣 사슬 전체가 같은 값
        flip_phase_deg: 180도 확정에 쓸 ``w = Z3 e^{-i3a}`` 의 위상 (0 또는 90). 형상 상수라
            부품마다 표가 듦. 프레임마다 값을 보고 고르면 판정 경계의 형상이 회전마다 선택을
            뒤집음 (실측 : 어떤 임계도 고정 0도보다 나쁨)
    """
    config_type: str = _FRAME_CFG
    object_type: str = _FRAME_NAME
    trainable: bool = False
    trust_radius: int = 224
    flip_phase_deg: float = 0.0


@MODELS.Register_module(_FRAME_NAME)
class Centroid_Frame(Trainable_Model):
    """이진 마스크 -> centroid + 주축각 + 신뢰도.

    - 주축각 = 2차 모멘트 닫힌 해 `0.5 atan2(2 Sxy, Sxx - Syy)` = k=2 harmonic `Z2` 의 위상 절반.
      n >= 3 회전대칭이면 `Z2 = 0` 이라 축 없음 -> `anisotropy` 로 보고
    - 180도 확정 = k=3 harmonic `Z3 = sum m (dx + i dy)^3` 의 주축 투영 부호. pi 회전에서 Z3 가
      부호를 뒤집는 유일한 저차 통계 (짝수 harmonic 과 원점 이동은 pi 회전 불변). 반쪽 분할류는
      `sign()` 불연속으로 근대칭에서 margin 이 노이즈에 잠겨 버림
    - 2회 대칭 형상은 어떤 통계로도 못 가름. `flip_margin` 이 그 미결정성을 보고

    전제 : 입력은 fill, 최대연결성분 처리 없는 원본. 관통 구멍은 형상 정보.
    """

    def Out_channels(self) -> list[int]:
        """center (2) / origin (2) / angle (1) / scale (1) / anisotropy (1) / flip_margin (1)."""
        return [2, 2, 1, 1, 1, 1]

    def Build(self, trust_radius: int = 224,
              flip_phase_deg: float = 0.0, **kwargs: Any) -> None:
        self.trust_radius = int(trust_radius)
        if self.trust_radius <= 0:
            raise ValueError(f"trust_radius 는 양수: {trust_radius}")
        self.flip_phase_deg = float(flip_phase_deg)
        self.norm = float(self.trust_radius)

    def forward(self, mask: Tensor) -> Frame:
        """
        Args:
            mask: (B, 1, H, W) float. 전경 1, 배경 0. 캔버스 크기 자유.

        Returns:
            :class:`Frame`.
        """
        _m = mask[:, 0]                                        # (B, H, W)
        _h, _w = mask.shape[-2], mask.shape[-1]
        _gy, _gx = _Grid(_h, _w, mask.device)

        _ux, _uy = _gx / self.norm, _gy / self.norm
        # 빈 마스크 가드. FP16 정규수 하한(6.1e-5)보다 큰 값. 그보다 작은 전경은 seg 의 min_area 가 거름
        _nm = _m.mean(dim=(1, 2)).clamp_min(1e-4)              # (B,) 전경 화소 비율

        _cx = (_m * _ux).mean(dim=(1, 2)) / _nm                # (B,) 무차원 centroid
        _cy = (_m * _uy).mean(dim=(1, 2)) / _nm

        _x = _ux - _cx.view(-1, 1, 1)                          # (B, H, W) centroid 기준
        _y = _uy - _cy.view(-1, 1, 1)
        _sxx = (_m * _x * _x).mean(dim=(1, 2)) / _nm
        _syy = (_m * _y * _y).mean(dim=(1, 2)) / _nm
        _sxy = (_m * _x * _y).mean(dim=(1, 2)) / _nm

        _z_re = _sxx - _syy
        _z_im = 2.0 * _sxy
        _angle = 0.5 * torch.atan2(_z_im, _z_re)               # (B,) 주축각, 180도 주기

        _trace = _sxx + _syy
        _scale = (_trace * 0.5).clamp_min(0.0).sqrt() * self.norm
        _aniso = _Abs2(_z_re, _z_im) / _trace.clamp_min(1e-12)

        _xx = _x * _x
        _yy = _y * _y
        _z3_re = (_m * _x * (_xx - 3.0 * _yy)).mean(dim=(1, 2))    # Re Z3
        _z3_im = (_m * _y * (3.0 * _xx - _yy)).mean(dim=(1, 2))    # Im Z3

        _c3, _s3 = torch.cos(3.0 * _angle), torch.sin(3.0 * _angle)
        _proj = _z3_re * _c3 + _z3_im * _s3                        # Re(w), 0도 성분

        _r2 = _xx + _yy
        _r3 = (_m * _r2 * _r2.sqrt()).mean(dim=(1, 2)).clamp_min(1e-12)
        _flip = _Abs2(_z3_re, _z3_im) / _r3                    # (B,) [0, 1]

        # 90도 성분 = Im(w) = 위상에 대한 기울기. 실수부가 0 을 지나는 형상(위상 -90도 근처)용
        if self.flip_phase_deg == 90.0:
            _proj = _z3_im * _c3 - _z3_re * _s3

        _angle = _angle + (_proj < 0).to(_angle.dtype) * torch.pi

        _center = torch.stack([_cx * self.norm + (_w - 1) / 2.0,
                               _cy * self.norm + (_h - 1) / 2.0], dim=1)
        _origin = _center.round().long()                       # 정수 양자화 (col, row)
        return Frame(
            center=_center, origin=_origin, angle=_angle, scale=_scale,
            anisotropy=_aniso, flip_margin=_flip,
        )


@CFGS.Register_module(_COORD_CFG)
@dataclass
class Frame_Coords_Config(Composable_Config):
    """정렬 좌표 ``(u, v)`` 산출 설정.

    Attributes:
        trust_radius: 길이 단위 상수 (px). `Region_Scalars` 와 같은 값 - 그쪽이 되곱해 px 로 되돌림
    """
    config_type: str = _COORD_CFG
    object_type: str = _COORD_NAME
    trainable: bool = False
    trust_radius: int = 224


@MODELS.Register_module(_COORD_NAME)
class Frame_Coords(Trainable_Model):
    """centroid 원점, 주축 정렬 좌표 ``(u, v)``. raster 회전 없이 좌표만 회전.

    `u` 는 주축 방향, `v` 는 그 수직. `norm` 으로 나눈 무차원 (FP16).
    """

    def Out_channels(self) -> list[int]:
        """u, v 두 텐서."""
        return [1, 1]

    def Build(self, trust_radius: int = 224, **kwargs: Any) -> None:
        self.trust_radius = int(trust_radius)
        if self.trust_radius <= 0:
            raise ValueError(f"trust_radius 는 양수: {trust_radius}")
        self.norm = float(self.trust_radius)

    def forward(self, mask: Tensor, frame: Frame) -> tuple[Tensor, Tensor]:
        """
        Args:
            mask: (B, 1, H, W) float. 좌표 격자 크기만 씀.
            frame: :class:`Frame`.

        Returns:
            ``(u, v)``. 각각 (B, H, W) float. `norm` 으로 나눈 무차원 좌표.
        """
        _h, _w = mask.shape[-2], mask.shape[-1]
        _gy, _gx = _Grid(_h, _w, mask.device)
        _cx = frame.center[:, 0].view(-1, 1, 1) - (_w - 1) / 2.0
        _cy = frame.center[:, 1].view(-1, 1, 1) - (_h - 1) / 2.0
        _ddx = (_gx - _cx) / self.norm
        _ddy = (_gy - _cy) / self.norm

        _cos = torch.cos(frame.angle).view(-1, 1, 1)
        _sin = torch.sin(frame.angle).view(-1, 1, 1)
        return _ddx * _cos + _ddy * _sin, -_ddx * _sin + _ddy * _cos
