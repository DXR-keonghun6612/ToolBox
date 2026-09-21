from __future__ import annotations

import torch.nn.functional as F
from torch import Tensor


def Cosine_sim(a: Tensor, b: Tensor) -> Tensor:
    """broadcast cosine 유사도. 정규화 후 마지막 차원 내적 -> (...,)."""
    return (F.normalize(a, dim=-1) * F.normalize(b, dim=-1)).sum(dim=-1)


def Pairwise_cosine(a: Tensor, b: Tensor | None = None) -> Tensor:
    """정규화 후 cosine 유사도 행렬. b 없으면 a 자기 자신과의 (K, K)."""
    _a = F.normalize(a, dim=-1)
    _b = _a if b is None else F.normalize(b, dim=-1)
    return _a @ _b.t()
