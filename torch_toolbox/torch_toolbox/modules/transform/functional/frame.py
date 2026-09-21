"""마스크 좌표계 (frame) 추정. 파라미터만, raster 회전 없음. 회전은 하류 (`Radial`) 의 theta 축 roll.
원점 = centroid, 정수 양자화. 극좌표와 해석적 측정이 같은 원점."""
from __future__ import annotations
from typing import NamedTuple

import torch
from torch import Tensor


_AREA_EPS = 1e-4         #: 전경 화소 비율 하한 (> FP16 정규수 하한)
_MOMENT_EPS = 1e-12      #: 모멘트 크기 하한


def _Abs2(re: Tensor, im: Tensor) -> Tensor:
    """|re + i im|. 하한 1e-12."""
    return (re * re + im * im).clamp_min(1e-24).sqrt()


def _Grid(h: int, w: int, device: torch.device) -> tuple[Tensor, Tensor]:
    """캔버스 기하중심 기준 픽셀 좌표 `(dy (1,H,1), dx (1,1,W))`."""
    _ys = torch.arange(h, dtype=torch.float32, device=device) - (h - 1) / 2.0
    _xs = torch.arange(w, dtype=torch.float32, device=device) - (w - 1) / 2.0
    return _ys.view(1, h, 1), _xs.view(1, 1, w)


def _Norm(trust_radius: int, px_size: float) -> float:
    """무차원화 `norm` (입력 px) = `trust_radius` (u) / `px_size` (u / 입력 px).

    Raises:
        ValueError: `trust_radius` 가 양수 아님, `px_size` 가 (0, 1] 밖.
    """
    if trust_radius <= 0:
        raise ValueError(f"trust_radius 는 양수: {trust_radius}")
    if not 0.0 < px_size <= 1.0:
        raise ValueError(f"px_size 는 (0, 1]: {px_size}. 입력 격자가 u 보다 거침")
    return float(trust_radius) / float(px_size)


class Frame(NamedTuple):
    """마스크 좌표계 파라미터.

    복원 : `Sxx + Syy = 2 scale^2`, `|Z2| = anisotropy 2 scale^2`,
    `lambda_+- = scale^2 (1 +- anisotropy)` (주축 / 부축 분산).

    Attributes:
        center: (B, 2) float. centroid (cx, cy). 입력 캔버스 px, sub-pixel
        origin: (B, 2) long. 정수 양자화한 극좌표 원점 (col, row)
        angle:  (B,) float. 주축각 (rad). 180도 확정 완료
        scale:  (B,) float. 회전반경 sqrt((Sxx+Syy)/2) (u). 회전 불변
        anisotropy:  (B,) float [0, 1]. k=2 harmonic 상대 크기 = `angle` 의 신뢰도.
            0 이면 주축 없음 (원환, n >= 3 회전대칭)
        flip_margin: (B,) float [0, 1]. k=3 harmonic 상대 크기 |Z3| / sum m r^3 = 180도 확정의
            신뢰도. 2회 회전대칭에서 0
    """

    center: Tensor
    origin: Tensor
    angle:  Tensor
    scale:  Tensor
    anisotropy:  Tensor
    flip_margin: Tensor


def Centroid_frame(mask: Tensor, *, trust_radius: int, px_size: float, flip_phase_deg: float) -> Frame:
    """이진 마스크 -> centroid + 주축각 + 신뢰도.

    - 주축각 = `0.5 atan2(2 Sxy, Sxx - Syy)` (k=2 harmonic `Z2` 위상의 절반)
    - 180도 확정 = k=3 harmonic `Z3 = sum m (dx + i dy)^3` 의 주축 투영 부호

    Args:
        mask: (B, 1, H, W) float. 전경 1, 배경 0. 캔버스 크기 자유.
        trust_radius: 읽는 반경 (u). 좌표 무차원화 기준.
        px_size: 입력 1 px 의 길이 / u. 상한 1.
        flip_phase_deg: 180도 확정에 쓰는 `w = Z3 e^{-i3a}` 의 위상 (0 또는 90). 부품별 상수.

    Returns:
        `Frame`.

    Raises:
        ValueError: `trust_radius` 가 양수 아님, `px_size` 가 (0, 1] 밖, `flip_phase_deg` 가 0, 90 아님.
    """
    _norm = _Norm(trust_radius, px_size)
    if flip_phase_deg not in (0.0, 90.0):
        raise ValueError(f"flip_phase_deg 는 0 또는 90: {flip_phase_deg}")

    _m = mask[:, 0]                                        # (B, H, W)
    _h, _w = mask.shape[-2], mask.shape[-1]
    _gy, _gx = _Grid(_h, _w, mask.device)

    _ux, _uy = _gx / _norm, _gy / _norm
    _nm = _m.mean(dim=(1, 2)).clamp_min(_AREA_EPS)         # (B,) 전경 화소 비율

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
    _scale = (_trace * 0.5).clamp_min(0.0).sqrt() * float(trust_radius)   # u
    _aniso = _Abs2(_z_re, _z_im) / _trace.clamp_min(_MOMENT_EPS)

    _xx = _x * _x
    _yy = _y * _y
    _z3_re = (_m * _x * (_xx - 3.0 * _yy)).mean(dim=(1, 2))    # Re Z3
    _z3_im = (_m * _y * (3.0 * _xx - _yy)).mean(dim=(1, 2))    # Im Z3

    _c3, _s3 = torch.cos(3.0 * _angle), torch.sin(3.0 * _angle)
    _r2 = _xx + _yy
    _r3 = (_m * _r2 * _r2.sqrt()).mean(dim=(1, 2)).clamp_min(_MOMENT_EPS)
    _flip = _Abs2(_z3_re, _z3_im) / _r3                    # (B,) [0, 1]

    # 0도 = Re(w), 90도 = Im(w)
    if flip_phase_deg == 90.0:
        _proj = _z3_im * _c3 - _z3_re * _s3
    else:
        _proj = _z3_re * _c3 + _z3_im * _s3

    _angle = _angle + (_proj < 0).to(_angle.dtype) * torch.pi

    _center = torch.stack([_cx * _norm + (_w - 1) / 2.0,
                           _cy * _norm + (_h - 1) / 2.0], dim=1)
    return Frame(
        center=_center, origin=_center.round().long(), angle=_angle, scale=_scale,
        anisotropy=_aniso, flip_margin=_flip,
    )


def Frame_coords(mask: Tensor, frame: Frame, *, trust_radius: int, px_size: float) -> tuple[Tensor, Tensor]:
    """centroid 원점, 주축 정렬 좌표 `(u, v)`. 좌표만 회전.

    Args:
        mask: (B, 1, H, W). 격자 크기만 사용.
        frame: `center` 와 `angle` 사용.
        trust_radius: `Centroid_frame` 과 같은 값.
        px_size: `Centroid_frame` 과 같은 값.

    Returns:
        `(u, v)`. 각각 (B, H, W) float. `u` 는 주축 방향, `v` 는 그 수직. `norm` 기준 무차원.

    Raises:
        ValueError: `trust_radius` 가 양수 아님, `px_size` 가 (0, 1] 밖.
    """
    _norm = _Norm(trust_radius, px_size)
    _h, _w = mask.shape[-2], mask.shape[-1]
    _gy, _gx = _Grid(_h, _w, mask.device)
    _cx = frame.center[:, 0].view(-1, 1, 1) - (_w - 1) / 2.0
    _cy = frame.center[:, 1].view(-1, 1, 1) - (_h - 1) / 2.0
    _ddx = (_gx - _cx) / _norm
    _ddy = (_gy - _cy) / _norm

    _cos = torch.cos(frame.angle).view(-1, 1, 1)
    _sin = torch.sin(frame.angle).view(-1, 1, 1)
    return _ddx * _cos + _ddy * _sin, -_ddx * _sin + _ddy * _cos
