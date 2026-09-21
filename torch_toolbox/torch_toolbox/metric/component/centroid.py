from __future__ import annotations
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor

from ..definition import Accumulator
from .. import ACCUMULATORS


@ACCUMULATORS.Register_module("centroid_accumulator")
class Centroid_Accumulator(Accumulator):
    """클래스별 평균 벡터. 메모리 O(K).

    Args:
        normalize: True 면 합산 전 단위구 투영 (구면 평균 방향), False 면 raw 합 (크기 가중).
    """

    def __init__(self, normalize: bool = True) -> None:
        self._normalize = normalize
        self._sums: dict[int, Tensor] = {}
        self._counts: dict[int, int] = {}

    def Update(self, *, embeddings: Tensor, gt_class_id: Tensor, **kwargs: Any) -> None:
        """
        Args:
            embeddings: (N, D).
            gt_class_id: (N,) 정수 class_id.
        """
        _vec = F.normalize(embeddings, dim=-1) if self._normalize else embeddings
        for _k in gt_class_id.unique():
            _kid = int(_k)
            _mask = gt_class_id == _k
            _v = _vec[_mask].sum(dim=0)
            if _kid in self._sums:
                self._sums[_kid] += _v
                self._counts[_kid] += int(_mask.sum())
            else:
                self._sums[_kid] = _v
                self._counts[_kid] = int(_mask.sum())

    def Finalize(self) -> tuple[Tensor, Tensor, Tensor]:
        """(means (K, D), class_ids (K,), counts (K,)). ids 오름차순."""
        _ids = sorted(self._sums)
        return (
            torch.stack([self._sums[_k] / self._counts[_k] for _k in _ids], dim=0),
            torch.tensor(_ids, dtype=torch.long),
            torch.tensor([self._counts[_k] for _k in _ids], dtype=torch.long),
        )

    def Reset(self) -> None:
        self._sums.clear()
        self._counts.clear()
