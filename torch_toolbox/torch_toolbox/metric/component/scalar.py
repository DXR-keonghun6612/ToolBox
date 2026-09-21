from __future__ import annotations
from typing import Any

import torch

from ..definition import Accumulator
from .. import ACCUMULATORS


@ACCUMULATORS.Register_module("scalar_accumulator")
class Scalar_Accumulator(Accumulator):
    """`(value, count)` 스칼라 쌍의 가중평균. 출력 중 `(int|float, int|float)` 2-튜플인 키만, 나머지는 무시."""

    def __init__(self) -> None:
        self._sums: dict[str, float] = {}
        self._counts: dict[str, float] = {}

    def Update(self, **output: Any) -> None:
        for _k, _v in output.items():
            if not (
                isinstance(_v, tuple) and len(_v) == 2
                and all(isinstance(_x, (int, float)) for _x in _v)
            ):
                continue
            _val, _cnt = float(_v[0]), float(_v[1])
            self._sums[_k] = self._sums.get(_k, 0.0) + _val * _cnt
            self._counts[_k] = self._counts.get(_k, 0.0) + _cnt

    def Finalize(self) -> dict[str, float]:
        """`{키: 가중평균}`. count 0 인 키 제외."""
        return {
            _k: self._sums[_k] / self._counts[_k]
            for _k in self._sums
            if self._counts[_k] > 0
        }

    def Is_diverged(self) -> bool:
        """가중평균 중 NaN / Inf 존재 여부."""
        return any(
            not torch.isfinite(torch.tensor(_v))
            for _v in self.Finalize().values()
        )

    def Reset(self) -> None:
        self._sums.clear()
        self._counts.clear()
