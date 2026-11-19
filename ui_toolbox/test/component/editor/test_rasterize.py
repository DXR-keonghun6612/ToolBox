"""raster 래스터화 - 픽셀 규약 흐름.

규약 : 픽셀 `(x, y)` 는 `[x, x + 1)`, 판정은 픽셀 가운데. 닫힌 도형은 가운데가 안에 있는 픽셀, 획은 가운데에서 궤적까지 거리가
반경 이하인 픽셀(반경 0 은 0.5).
"""

from __future__ import annotations

import numpy as np
import pytest

from ui_toolbox.component.editor.raster._ops import Rasterize


def test_rasterize_flow():
    # 단계 : 닫힌 사각형 - 경계에 걸친 픽셀을 안 칠함
    _rect = Rasterize(np.array([[10.0, 10.0], [30.0, 10.0], [30.0, 20.0], [10.0, 20.0]]), True, 0.0, (40, 40))
    _ys, _xs = np.nonzero(_rect)
    assert _rect.sum() == 200, f"rect: area {_rect.sum()} - expected 20 x 10"
    assert (_xs.min(), _xs.max(), _ys.min(), _ys.max()) == (10, 29, 10, 19), "rect: painted bounds"

    # 단계 : 닫힌 삼각형 - 가운데가 x + y < 10 안인 픽셀 수
    _tri = Rasterize(np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]]), True, 0.0, (12, 12))
    assert _tri.sum() == 45, f"triangle: area {_tri.sum()}"

    # 단계 : 점 하나 획 - 반경 2 원
    _dot = Rasterize(np.array([[5.5, 5.5]]), False, 2.0, (12, 12))
    assert _dot.sum() == 13, f"dot stroke: area {_dot.sum()}"
    assert _dot[5, 5], "dot stroke: center pixel"

    # 단계 : 반경 0 선 - 한 픽셀 폭
    _line = Rasterize(np.array([[2.0, 5.5], [9.0, 5.5]]), False, 0.0, (12, 12))
    assert set(np.nonzero(_line)[0]) == {5}, "radius 0 line: one row"

    # 단계 : 닫힌 도형 + 반경 - 둘레를 더 칠함
    _thick = Rasterize(np.array([[10.0, 10.0], [30.0, 10.0], [30.0, 20.0], [10.0, 20.0]]), True, 2.0, (40, 40))
    assert _thick.sum() > _rect.sum() and _thick[_rect].all(), "closed + radius: covers inside, wider"

    # 단계 : 영상 밖 - 잘림
    _edge = Rasterize(np.array([[-5.0, -5.0], [3.0, 3.0]]), False, 1.0, (4, 4))
    assert _edge.shape == (4, 4) and _edge[0, 0], "outside image: paints inside only"

    # 실패 갈래 : 잘못된 입력
    for _v, _r in ((np.zeros((0, 2)), 1.0), (np.zeros((3, 3)), 1.0), (np.zeros((2, 2)), -1.0)):
        with pytest.raises(ValueError):
            Rasterize(_v, False, _r, (5, 5))
