from __future__ import annotations
from dataclasses import dataclass
import warnings
from typing import Any

import torch
from torch import Tensor
from torch.nn import functional as F

from ..... import CFGS
from .... import MODELS
from ....definition import Composable_Config
from ....model.definition import Trainable_Model

from ..canonical import Centroid_Frame, Frame_Coords
from .moment import Chirality_Moments
from .region import Region_Scalars
from ..occupancy import Occupancy, Radial_Profile, Radial_RLE
from ..polar import Polar_Raster

"""실루엣 마스크 -> geometry 토큰. torch 단일 소스라 학습, 추론, 배포가 같은 그래프.

파이프라인::

    mask -> Centroid_Frame   (centroid, 주축각. 파라미터만)
         -> Frame_Coords     (정렬 좌표 u, v. 무차원)
         -> Polar_Raster     (backward gather, occupancy 분수)
         -> Radial_Profile / Region_Scalars / Chirality_Moments / Occupancy / Radial_RLE

- 길이 단위 상수 `trust_radius` 하나. 입력 캔버스 크기는 값에 안 남음
- 차원은 하드코딩 없음. 서브모듈이 `Feature_Spec` 으로 선언하고 여기서 합산
"""


_NAME = "geometry_embedding"
_CFG  = f"{_NAME}_Config"


def _signed(rle: Tensor) -> Tensor:
    """RLE 간격 ``(B, NT, K)`` -> 부호합 ``(B, NT)`` = 살합 - 빈공간합.

    슬롯은 안쪽부터 [시작r, 살1, 구멍1, ...] 라 짝수 자리가 빈 공간, 홀수가 살.
    광선이 구멍을 스칠 때 rle 는 슬롯이 밀려 계단으로 뛰지만 부호합은 연속.
    """
    _sign = torch.where(
        torch.arange(rle.shape[-1], device=rle.device) % 2 == 1, 1.0, -1.0)
    return (rle * _sign).sum(-1)


#: radial 도메인 -> RLE ``(B, NT, K)`` 를 접는 법. 구멍을 얼마나 보느냐로 갈림::
#:
#:     rle      (NT, K)  밴드 배치까지     구멍 위치까지 같아야 같음
#:     signed   (NT,)    살합 - 빈합       구멍 총량이 같으면 같음
#:     outline  (NT,)    sum(2)           실루엣만 같으면 같음
#:
#: 새 접기 = 여기 한 줄 + config `radial_domains` 한 항목
RADIAL_FOLDS = {
    "rle":     lambda _r: _r,
    "signed":  _signed,
    "outline": lambda _r: _r.sum(-1),
}

#: 생성 그룹 -> 데이터 그룹 (물리량 종류). 같은 key 끼리 pool, 표시 단위. 매핑에 없으면 자기 이름.
#: radial 계열은 전부 px 반경이라 한 pool 이어야 outer-inner 간격이 표준화로 안 사라짐.
#: area 는 1/r 가중이 섞여 size 와 의미가 달라 그룹 유지
DATA_GROUP: dict[str, str] = {
    "radial_outer": "radius", "radial_inner": "radius",
    "outer_stats": "radius", "inner_stats": "radius", "thickness_stats": "radius",
    "coverage_stats": "coverage",
    "area_cartesian_sqrt": "area", "area_polar_sqrt": "area",
    "area_ratio": "ratio", "ratio": "ratio",
    "chirality": "moment", "moments": "moment",
    "position": "position", "size": "size",
    "outer_fft_mag": "spectral_mag", "inner_fft_mag": "spectral_mag",
    "outer_fft_phase": "spectral_phase", "inner_fft_phase": "spectral_phase",
}


@CFGS.Register_module(_CFG)
@dataclass
class Geometry_Embedding_Config(Composable_Config):
    """극좌표 기반 형상 토큰 설정.

    Attributes:
        trust_radius: 샘플 반경 (px, 정수). 이 안은 1 px 간격으로 전부 읽고 밖은 안 읽음.
            길이 단위 상수(FP16 무차원화 `norm`)이기도 함. 바꾸면 토큰 공간이 바뀜
        num_angular: theta bin 수 `NT` = 각도 토큰 수
        sub: 극좌표 셀당 축별 sub-sample 수. 바깥쪽 얇은 구멍 민감도
        occupancy_threshold: 셀을 "재료 있음" 으로 볼 occupancy 분수 하한
        radial_domains: 낼 radial 도메인. :data:`RADIAL_FOLDS` 의 key. 산출물 서명에 들어감 -
            코드가 도메인을 몰래 늘리면 옛 산출물이 새 계약을 달고 남음
        max_transitions: radial_rle theta 당 슬롯 수 `K`
        variance_warn: 토큰 그룹 차원 편차 경고 배율
    """
    config_type: str = _CFG
    object_type: str = _NAME
    trainable: bool = False
    trust_radius: int = 224
    num_angular: int = 512
    sub: int = 1
    occupancy_threshold: float = 0.5
    radial_domains: tuple[str, ...] = ("rle",)
    max_transitions: int = 8
    variance_warn: float = 3.0


@MODELS.Register_module(_NAME)
class Geometry_Embedding(Trainable_Model):
    """``(B, 1, H, W)`` 이진 마스크 -> geometry 토큰.

    전제 : 입력은 fill, 최대연결성분 처리 없는 원본. 관통 구멍은 형상 정보.
    """

    def Build(
        self,
        trust_radius: int = 224,
        num_angular: int = 512,
        sub: int = 1,
        occupancy_threshold: float = 0.5,
        radial_domains: tuple[str, ...] = ("rle",),
        max_transitions: int = 8,
        variance_warn: float = 3.0,
        **kwargs: Any,
    ) -> None:
        _K = dict(trainable=False, trust_radius=trust_radius)
        self.frame  = Centroid_Frame(name="frame", **_K)
        self.coords = Frame_Coords(name="coords", **_K)
        self.polar  = Polar_Raster(name="polar", num_angular=num_angular, sub=sub, **_K)
        self.radial = Radial_Profile(name="radial", trainable=False, threshold=occupancy_threshold)

        self.region = Region_Scalars(name="region", num_angular=num_angular, **_K)
        self.moment = Chirality_Moments(name="moment", trainable=False)
        self.occ    = Occupancy(name="occ", num_angular=num_angular, **_K)
        self.rle    = Radial_RLE(
            name="rle", trainable=False, threshold=occupancy_threshold,
            max_transitions=max_transitions)

        _unknown = [_d for _d in radial_domains if _d not in RADIAL_FOLDS]
        if _unknown:
            raise KeyError(f"모르는 radial 도메인 {_unknown} (가능: {sorted(RADIAL_FOLDS)})")
        self.radial_domains = tuple(radial_domains)

        self._variance_warn = float(variance_warn)
        self._global = ["region", "moment", "occ"]
        _dims = self._global_group_dims()
        _dims["radial_rle"] = int(max_transitions)
        self._token_dim = max(_dims.values())
        self._warn_variance(_dims)

    def _global_group_dims(self) -> dict[str, int]:
        """전역 descriptor 를 data_group 으로 재묶었을 때의 그룹별 차원."""
        _dims: dict[str, int] = {}
        for _name in self._global:
            for _s in getattr(self, _name).Spec():
                _dg = DATA_GROUP.get(_s.name, _s.name)
                _dims[_dg] = _dims.get(_dg, 0) + _s.dim
        return _dims

    def _warn_variance(self, dims: dict[str, int]) -> None:
        """그룹 간 차원 편차가 크면 경고. 결합 실수 힌트."""
        if not dims:
            return
        _mx, _mn = max(dims.values()), min(dims.values())
        if _mx >= self._variance_warn * max(_mn, 1):
            warnings.warn(
                f"토큰 그룹 차원 편차 큼 (max {_mx} / min {_mn}). 패딩 낭비, 결합 실수 가능. "
                f"그룹별: {dims}", stacklevel=2)

    @property
    def token_dim(self) -> int:
        """토큰 하나의 차원 = max(전역 그룹, rle 슬롯)."""
        return self._token_dim

    @property
    def token_groups(self) -> list[tuple[str, str]]:
        """토큰 순서 -> ``(data_group, axis)``. 전역(scalar) 먼저, 각도(radial_rle) NT 개."""
        _g = [(_dg, "scalar") for _dg in self._global_group_dims()]
        _nt = self.polar.num_angular
        return _g + [("radial_rle", "angular")] * _nt

    def Out_channels(self) -> list[int]:
        """토큰 차원."""
        return [self._token_dim]

    def Occupancy_grid(self, mask: Tensor) -> Tensor:
        """이진 마스크 -> 극좌표 occupancy 격자 ``(B, NR, NT)``. 시각화용."""
        return self.polar(mask, self.frame(mask))

    def _pad(self, x: Tensor) -> Tensor:
        """``(B, d)`` -> ``(B, 1, token_dim)`` 뒤 패딩."""
        _d = x.shape[1]
        if _d < self._token_dim:
            x = F.pad(x, (0, self._token_dim - _d))
        return x.unsqueeze(1)

    def Features(self, mask: Tensor) -> dict[str, Tensor]:
        """``(B, 1, H, W)`` 마스크 -> 도메인별 native feature dict. 병합, 패딩 없음.

        순서 없는 scalar 그룹은 ``(B, dim)``, radial_rle 은 ``(B, NT, K)``. 조립은 소비처 책임.
        정규화 전 raw (px, 무차원 비). 정규화는 소비처가 선형 scale 로.
        도메인 성질은 :attr:`domain_kinds`.
        """
        _frame = self.frame(mask)
        _u, _v = self.coords(mask, _frame)
        _polar = self.polar(mask, _frame)
        _prof  = self.radial(_polar)

        _flat = {
            "region": (self.region(mask, _u, _v, _prof), self.region.Spec()),
            "moment": (self.moment(mask, _u, _v),        self.moment.Spec()),
            "occ":    (self.occ(mask, _polar),           self.occ.Spec()),
        }
        _by_dg: dict[str, list[Tensor]] = {}
        for _name in self._global:
            _out, _specs = _flat[_name]
            _at = 0
            for _s in _specs:
                _dg = DATA_GROUP.get(_s.name, _s.name)
                _by_dg.setdefault(_dg, []).append(_out[:, _at: _at + _s.dim])
                _at += _s.dim

        _feats: dict[str, Tensor] = {_dg: torch.cat(_by_dg[_dg], dim=1)
                                     for _dg in self._global_group_dims()}
        _rle = self.rle(_polar)
        for _name in self.radial_domains:
            _feats[f"radial_{_name}"] = RADIAL_FOLDS[_name](_rle)
        return _feats

    @property
    def domain_kinds(self) -> dict[str, str]:
        """도메인 -> 성질 (``FEATURE`` 순서 없음 / ``TOKEN`` 순서 있음)."""
        from ....feature._base import FEATURE, TOKEN
        _kinds = {_dg: FEATURE for _dg in self._global_group_dims()}
        for _name in self.radial_domains:
            _kinds[f"radial_{_name}"] = TOKEN
        return _kinds

    def Tokens(self, mask: Tensor) -> Tensor:
        """``(B, 1, H, W)`` 마스크 -> ``(B, seq, token_dim)`` 병합 토큰. 도메인별 max 차원 패딩.

        검증은 이 병합을 쓰지 않음 (도메인별 스케일이 패딩으로 뭉개짐). :meth:`Features` 로.
        """
        _feats = self.Features(mask)
        _tokens = [self._pad(_feats[_dg]) for _dg in self._global_group_dims()]
        _ang = _feats["radial_rle"]
        if _ang.shape[-1] < self._token_dim:
            _ang = F.pad(_ang, (0, self._token_dim - _ang.shape[-1]))
        return torch.cat([*_tokens, _ang], dim=1)                 # (B, alpha+NT, token_dim)

    def forward(self, mask: Tensor) -> Tensor:
        """
        Args:
            mask: (B, 1, H, W) float. 전경 1, 배경 0.

        Returns:
            (B, seq, token_dim) float. raw 토큰.
        """
        return self.Tokens(mask)
