from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

"""feature 선언과 정규화.

파이프라인 순서를 고정한다::

    descriptor (raw, 원본 스케일)  ->  transform (identity)  ->  normalize (offset, scale, 선형)

- descriptor 모듈은 **raw 값만** 낸다. 정규화를 계산식 안에 섞지 않는다.
- ``transform`` 은 이제 **전부 identity** 다. 예전엔 ``log1p``/``slog`` 로 자릿수를 압축했으나,
  이 feature 는 **형상 정보**라 log 같은 비선형이 형상을 뭉갠다(절대 크기·비율 왜곡). 그래서
  압축을 걷어냈다 — 자릿수 차이는 log 가 아니라 그룹별 선형 ``scale`` 로 흡수한다(``value_range``).
  필드는 남겨 두되(그래프 구조 불변) 값은 identity 로 고정한다.
- ``normalize`` 는 **표시·학습용 선형 scale** 이다. ``(x - offset) / scale`` 을 한 번 적용하고,
  그 상수는 buffer 라 export 직전에 갈아끼울 수 있다. **저장은 정규화 전 원본값**(``Raw``)이고,
  정규화는 볼 때/학습할 때 적용한다 — 그래야 언제 뽑은 데이터든 같은 scale 을 쓰고 절대 크기를
  잃지 않는다.

``FEAT_DIM`` 과 그룹 슬라이스를 하드코딩하지 않는 이유: 기존 ``sample_extractor`` 는
``FEAT_DIM = 426`` 과 ``FEAT_GROUPS`` 슬라이스가 리터럴이라 ``num_angles`` 를 바꾸면
조용히 어긋났다. 여기서는 모듈이 자기 spec 을 선언하고 조립기가 합산한다.
"""


@dataclass(frozen=True)
class Feature_Spec:
    """feature 그룹 하나의 선언.

    Attributes:
        name: 그룹 이름.
        dim: 차원 수.
        transform: ``identity`` | ``log1p`` | ``slog``.
        value_range: **transform 적용 후** 범위 ``(lo, hi)``.
        axis: 이 그룹의 값 축 종류. ``"scalar"``(기본, 순서 없는 스칼라 묶음) |
            ``"angular"``(θ 색인 프로파일 — dim 개 값이 각도축을 등분한다. 극좌표 r-θ 로 그리면
            실루엣 외곽이 보인다). 소비처가 크기로 추측하지 않고 이 선언으로 각도축을 안다.
    """

    name: str
    dim: int
    transform: str
    value_range: tuple[float, float]
    axis: str = "scalar"


def Apply_transform(x: Tensor, kind: str) -> Tensor:
    """그룹별 자릿수 압축. ``slog`` 는 부호를 보존한다."""
    if kind == "identity":
        return x
    if kind == "log1p":
        return torch.log1p(x.clamp_min(0.0))
    if kind == "slog":
        return torch.sign(x) * torch.log1p(x.abs())
    raise ValueError(f"알 수 없는 transform: {kind}")


class Normalizer(nn.Module):
    """선언된 spec 에서 그룹별 ``(offset, scale)`` 을 만들어 마지막에 한 번 적용하는 **선형** 정규화.

    **정규화는 embedding forward 에서 분리돼 있다** — descriptor 는 raw(원본 스케일)를 내고, 이 모듈이
    학습·배포 그래프 앞단에 융합돼 config scale 로 정규화한다. 저장·분석은 raw 를 쓴다(절대 크기 보존).

    scale 기본값은 각 spec 의 **이론 범위**(선형)에서 나오고, ``Set_scale`` 로 그룹별 config 상수를
    override 할 수 있다(안 적은 그룹은 이론값). 데이터 통계가 아니라 **상수** 라, 언제 뽑은 데이터든
    같은 scale 을 쓴다.

    Args:
        specs: 이어붙일 순서대로의 :class:`Feature_Spec`.
    """

    def __init__(self, specs: tuple[Feature_Spec, ...]) -> None:
        super().__init__()
        self.specs = specs

        _off, _scl = [], []
        for _s in specs:
            _lo, _hi = _s.value_range
            _mid = (_lo + _hi) / 2.0
            _half = max((_hi - _lo) / 2.0, 1e-6)
            _off += [_mid] * _s.dim
            _scl += [_half] * _s.dim
        self.register_buffer("offset", torch.tensor(_off, dtype=torch.float32), persistent=False)
        self.register_buffer("scale",  torch.tensor(_scl, dtype=torch.float32), persistent=False)

    @torch.no_grad()
    def Set_scale(self, group_scale: dict[str, float]) -> None:
        """그룹별 scale 상수를 config 값으로 override 한다 (안 적은 그룹은 이론값 유지).

        offset 은 그대로 두고 scale 만 바꾼다 — 원본이 [0, hi] 인 형상량은 offset 없이 scale 로만
        [0, 1] 근방에 두는 게 자연스럽다(부호 있는 그룹은 spec range 가 대칭이라 offset=0).

        Args:
            group_scale: ``{그룹명: scale}``. 그 그룹의 모든 dim 에 같은 상수를 건다.
        """
        _at = 0
        for _s in self.specs:
            if _s.name in group_scale:
                _v = max(float(group_scale[_s.name]), 1e-6)
                self.scale[_at: _at + _s.dim] = _v
            _at += _s.dim

    def forward(self, x: Tensor) -> Tensor:
        """(B, FEAT_DIM) raw(=transform 적용 후) -> 정규화."""
        return (x - self.offset) / self.scale
