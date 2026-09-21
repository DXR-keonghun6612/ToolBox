from __future__ import annotations

from torch import Tensor


def Vmf_concentration(
    means: Tensor, dim: int | None = None, eps: float = 1e-6
) -> tuple[Tensor, Tensor]:
    """평균 resultant length `R = ||means||` 와 von Mises-Fisher 농도 (Banerjee 근사 `R (p - R^2) / (1 - R^2)`).

    Args:
        means: (K, D) 단위벡터 그룹 평균 (미정규화). 예 `Centroid_Accumulator(normalize=True).Finalize()`.
        dim: 차원 p. None 이면 `means.shape[-1]`.
        eps: `1 - R^2` 하한.

    Returns:
        (R (K,), kappa (K,)).
    """
    _R = means.norm(dim=-1)
    _p = means.shape[-1] if dim is None else dim
    _kappa = _R * (_p - _R**2) / (1.0 - _R**2).clamp(min=eps)
    return _R, _kappa
