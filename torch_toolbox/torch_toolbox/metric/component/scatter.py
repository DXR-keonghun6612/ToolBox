from __future__ import annotations
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor

from ..definition import Accumulator
from .. import ACCUMULATORS


def Oas_shrinkage(cov: Tensor, dof: int) -> float:
    """OAS shrinkage 계수 `r` (닫힌 식). `Sigma_hat = (1-r)*S + r*(tr S/d)*I`. `tr(S)`, `tr(S^2)`, 자유도만 사용.

    Args:
        cov: (d, d) 대칭 공분산.
        dof: 추정 자유도. 클래스 내 풀링이면 `표본 수 - 클래스 수`.

    Returns:
        `[0, 1]`. `S` 가 등방이면 1.

    Raises:
        ValueError: `cov` 가 정사각 아님, `dof < 1`.
    """
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError(f"cov 는 정사각이어야 한다: {tuple(cov.shape)}")
    if dof < 1:
        raise ValueError(f"자유도가 1 미만이다: {dof}")

    _s = cov.double()
    _d = _s.shape[0]
    _tr = torch.diagonal(_s).sum()
    _tr_sq = (_s * _s).sum()                      # tr(S^2), S 대칭

    _den = (dof + 1 - 2.0 / _d) * (_tr_sq - _tr ** 2 / _d)
    if _den <= 0:
        return 1.0

    _num = (1 - 2.0 / _d) * _tr_sq + _tr ** 2
    return float(torch.clamp(_num / _den, 0.0, 1.0))


def _Batch_moments(values: Tensor) -> tuple[int, float, float, float]:
    """(n,) 스칼라 -> `(n, mean, M2, M3)`. `M_j` 는 중심 j 차 적률의 합."""
    _n = int(values.numel())
    _mean = values.mean()
    _dev = values - _mean
    return (
        _n, float(_mean), float((_dev ** 2).sum()), float((_dev ** 3).sum()),
    )


def _Merge_moments(
    a: tuple[int, float, float, float] | None, b: tuple[int, float, float, float],
) -> tuple[int, float, float, float]:
    """두 묶음의 `(n, mean, M2, M3)` 병합 (Chan / Pebay)."""
    if a is None:
        return b
    _na, _ma, _m2a, _m3a = a
    _nb, _mb, _m2b, _m3b = b
    _n = _na + _nb
    _d = _mb - _ma
    return (
        _n,
        _ma + _d * _nb / _n,
        _m2a + _m2b + _d ** 2 * _na * _nb / _n,
        (
            _m3a + _m3b
            + _d ** 3 * _na * _nb * (_na - _nb) / _n ** 2
            + 3.0 * _d * (_na * _m2b - _nb * _m2a) / _n
        ),
    )


@ACCUMULATORS.Register_module("within_class_scatter_accumulator")
class Within_Class_Scatter_Accumulator(Accumulator):
    """클래스별 평균 + 클래스 내 공분산 풀링 + (선택) 클래스별 스칼라 1 ~ 3차 모멘트. 한 패스.

    - 스캐터는 공유 `(D, D)` 하나. 배치마다 배치 평균 기준 중심화 후 평균 차이 보정 (Chan 병합). `float64`
    - 스칼라 모멘트는 `Finalize_scalar` 로 따로

    Args:
        normalize: True 면 합산 전 단위구 투영 (코사인 헤드용), False 면 raw (FC 헤드용).
    """

    def __init__(self, normalize: bool = True) -> None:
        self._normalize = normalize
        self._means: dict[int, Tensor] = {}
        self._counts: dict[int, int] = {}
        self._scatter: Tensor | None = None
        #: class_id -> (n, mean, M2, M3). `class_scalar` 를 안 받으면 비어 있음
        self._scalar: dict[int, tuple[int, float, float, float]] = {}

    def Update(
        self,
        *,
        embeddings: Tensor,
        gt_class_id: Tensor,
        class_scalar: Tensor | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            embeddings: (N, D).
            gt_class_id: (N,) 정수 class_id.
            class_scalar: (N,) 표본별 스칼라. None 이면 스칼라 모멘트 누적 없음.
        """
        _vec = F.normalize(embeddings, dim=-1) if self._normalize else embeddings
        _vec = _vec.detach().double()
        if self._scatter is None:
            _d = _vec.shape[1]
            self._scatter = torch.zeros(_d, _d, dtype=torch.float64, device=_vec.device)

        _scalar = None if class_scalar is None else class_scalar.detach().double()

        for _k in gt_class_id.unique():
            _kid = int(_k)
            _mask = gt_class_id == _k
            if _scalar is not None:
                self._scalar[_kid] = _Merge_moments(
                    self._scalar.get(_kid), _Batch_moments(_scalar[_mask]))

            _batch = _vec[_mask]
            _nb = _batch.shape[0]
            _mb = _batch.mean(dim=0)

            _resid = _batch - _mb
            self._scatter += _resid.T @ _resid

            _na = self._counts.get(_kid, 0)
            if _na == 0:
                self._means[_kid] = _mb
                self._counts[_kid] = _nb
                continue

            # Chan 병합의 평균 차이 항
            _delta = _mb - self._means[_kid]
            self._scatter += (_na * _nb / (_na + _nb)) * torch.outer(_delta, _delta)
            self._means[_kid] = self._means[_kid] + _delta * (_nb / (_na + _nb))
            self._counts[_kid] = _na + _nb

    def Finalize(self) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        """
        Returns:
            (mean (K, D), class_ids (K,), within_cov (D, D), counts (K,)).
            ids 오름차순. `within_cov` 는 `N - K` 로 나눈 불편추정.

        Raises:
            RuntimeError: 누적 없음, 또는 자유도 `N - K <= 0`.
        """
        if self._scatter is None or not self._counts:
            raise RuntimeError(
                "누적된 표본이 없다 — Update 가 한 번도 불리지 않았다."
            )
        _ids = sorted(self._means)
        _n = sum(self._counts.values())
        _dof = _n - len(_ids)
        if _dof <= 0:
            raise RuntimeError(
                f"자유도가 없다 (표본 {_n}, 클래스 {len(_ids)}). 클래스당 2개 이상 필요하다."
            )
        return (
            torch.stack([self._means[_k] for _k in _ids], dim=0).float(),
            torch.tensor(_ids, dtype=torch.long),
            (self._scatter / _dof).float(),
            torch.tensor([self._counts[_k] for _k in _ids], dtype=torch.long),
        )

    def Finalize_scalar(self) -> tuple[Tensor, Tensor]:
        """`class_scalar` 의 클래스별 표준편차와 왜도. `Finalize` 와 같은 id 순서.

        Returns:
            (std (K,), skew (K,)). 미정의는 NaN : std 는 `n < 2`, skew 는 `n < 3` 또는 산포 0.
            `class_scalar` 를 안 받았으면 전부 NaN.

        Raises:
            RuntimeError: 누적 없음.
        """
        if not self._counts:
            raise RuntimeError(
                "누적된 표본이 없다 — Update 가 한 번도 불리지 않았다."
            )
        _nan = float("nan")
        _std: list[float] = []
        _skew: list[float] = []
        for _k in sorted(self._means):
            _mom = self._scalar.get(_k)
            if _mom is None or _mom[0] < 2:
                _std.append(_nan)
                _skew.append(_nan)
                continue
            _n, _, _m2, _m3 = _mom
            _std.append((_m2 / (_n - 1)) ** 0.5)
            # 표본 왜도 g1
            _skew.append(
                _m3 / _n / (_m2 / _n) ** 1.5 if _n >= 3 and _m2 > 0 else _nan)
        return (
            torch.tensor(_std, dtype=torch.float32),
            torch.tensor(_skew, dtype=torch.float32),
        )

    def Reset(self) -> None:
        self._means.clear()
        self._counts.clear()
        self._scalar.clear()
        self._scatter = None
