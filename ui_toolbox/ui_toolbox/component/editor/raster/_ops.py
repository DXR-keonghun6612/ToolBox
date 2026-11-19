"""raster 연산 - 꼭짓점을 픽셀로 찍음. 미리보기와 받는 쪽이 같은 함수.

UI 를 모름 - numpy 만.

좌표는 원본 픽셀 실수 - 픽셀 `(x, y)` 는 `[x, x + 1) x [y, y + 1)`. 판정은 픽셀 가운데 `(x + 0.5, y + 0.5)` 로.
- 닫힌 도형 : 가운데가 안에 있는 픽셀. 행마다 가운데 높이에서 변과 만나는 점 사이를 반열린 구간으로
- 획 : 가운데에서 궤적까지 거리가 반경 이하인 픽셀. 반경 0 은 0.5 - 한 픽셀 폭
"""

from __future__ import annotations

import numpy as np

__all__ = ["Rasterize"]


def _fill(v: np.ndarray, mask: np.ndarray) -> None:
    """닫힌 도형 `v` 의 안을 `mask` 에 칠함. 짝홀 규칙."""
    _h, _w = mask.shape
    _a, _b = v, np.roll(v, -1, axis=0)                 # 변 a -> b
    _lo = max(0, int(np.floor(v[:, 1].min() - 0.5)))
    _hi = min(_h, int(np.ceil(v[:, 1].max() + 0.5)))
    for _y in range(_lo, _hi):
        _c = _y + 0.5
        # 꼭짓점을 두 번 안 세게 아래는 닫고 위는 엶
        _hit = (np.minimum(_a[:, 1], _b[:, 1]) <= _c) & (_c < np.maximum(_a[:, 1], _b[:, 1]))
        if not _hit.any():
            continue
        _ea, _eb = _a[_hit], _b[_hit]
        _xs = np.sort(_ea[:, 0] + (_c - _ea[:, 1]) * (_eb[:, 0] - _ea[:, 0]) / (_eb[:, 1] - _ea[:, 1]))
        for _x0, _x1 in zip(_xs[0::2], _xs[1::2]):
            # 가운데 x + 0.5 가 [x0, x1) 안인 픽셀
            _s = max(0, int(np.ceil(_x0 - 0.5)))
            _e = min(_w, int(np.ceil(_x1 - 0.5)))
            if _e > _s:
                mask[_y, _s:_e] = True


def _stroke(v: np.ndarray, radius: float, mask: np.ndarray) -> None:
    """궤적 `v` 에서 반경 안인 픽셀을 `mask` 에 칠함. 선분마다 그 둘레 창만 잼."""
    _h, _w = mask.shape
    _segs = [(v[0], v[0])] if len(v) == 1 else list(zip(v[:-1], v[1:]))
    for _p, _q in _segs:
        _x0 = max(0, int(np.floor(min(_p[0], _q[0]) - radius)))
        _x1 = min(_w, int(np.ceil(max(_p[0], _q[0]) + radius)) + 1)
        _y0 = max(0, int(np.floor(min(_p[1], _q[1]) - radius)))
        _y1 = min(_h, int(np.ceil(max(_p[1], _q[1]) + radius)) + 1)
        if _x1 <= _x0 or _y1 <= _y0:
            continue
        _gx, _gy = np.meshgrid(np.arange(_x0, _x1) + 0.5, np.arange(_y0, _y1) + 0.5)
        _d = _q - _p
        _len2 = float(_d @ _d)
        _t = 0.0 if _len2 == 0 else np.clip(((_gx - _p[0]) * _d[0] + (_gy - _p[1]) * _d[1]) / _len2, 0, 1)
        _dist2 = (_gx - (_p[0] + _t * _d[0])) ** 2 + (_gy - (_p[1] + _t * _d[1])) ** 2
        mask[_y0:_y1, _x0:_x1] |= _dist2 <= radius * radius


def Rasterize(vertices: np.ndarray, closed: bool, radius: float,
              shape: tuple[int, int]) -> np.ndarray:
    """꼭짓점을 `(H, W)` bool 로 찍음.

    Args:
        vertices: `(N, 2)` 원본 픽셀 `(x, y)`.
        closed: 닫힘 - 안을 채움.
        radius: 선 반경(px). 0 이면 한 픽셀 폭. 닫힌 것은 반경이 있을 때만 둘레를 더 칠함.
        shape: 영상 `(H, W)`.

    Raises:
        ValueError: `vertices` 가 `(N, 2)` 가 아니거나 비었을 때, `radius` 가 음수일 때.
    """
    _v = np.asarray(vertices, dtype=float)
    if _v.ndim != 2 or _v.shape[1] != 2 or len(_v) == 0:
        raise ValueError(f"vertices must be (N, 2) - got shape {_v.shape}")
    if radius < 0:
        raise ValueError(f"radius must be >= 0 - got {radius}")
    _mask = np.zeros(shape, bool)
    if closed and len(_v) >= 3:
        _fill(_v, _mask)
        if radius == 0:
            return _mask
        _stroke(np.vstack([_v, _v[:1]]), radius, _mask)
        return _mask
    _stroke(_v, radius if radius > 0 else 0.5, _mask)
    return _mask
