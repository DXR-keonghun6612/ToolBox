from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any

import torch
from torch import Tensor

from ..... import CFGS
from .... import MODELS
from ....definition import Composable_Config
from ....model.definition import Trainable_Model

from .spec import Feature_Spec

"""주기 프로파일 통계 — mean/std/min/max/range + 백분위(10·25·50·75·90).

기존 ``_profile_stats`` 는 ``np.percentile(..., method='linear')`` 을 썼다. 프로파일 길이가
``NT`` 로 **고정**이므로 백분위 위치 ``q * (N-1)`` 도 상수다. 따라서 정렬 후 고정 인덱스
두 개를 뽑아 선형보간하면 끝이고, 상수 인덱스·가중치는 buffer 로 미리 잡는다.

ONNX 에서는 정렬이 ``TopK`` 로 나간다. 별도 quantile 연산이 필요 없다.
"""

_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
STAT_NAMES = ("mean", "std", "min", "max", "range", "p10", "p25", "p50", "p75", "p90")


_PROFILE_STATS_NAME = "profile_stats"
_PROFILE_STATS_CFG  = f"{_PROFILE_STATS_NAME}_Config"


@CFGS.Register_module(_PROFILE_STATS_CFG)
@dataclass
class Profile_Stats_Config(Composable_Config):
    """주기 프로파일 통계 설정.

    Attributes:
        length: 프로파일 길이 ``N``(= num_angular). 백분위 인덱스를 상수로 굳힌다.
        quantiles: 백분위 목록. 개수를 바꾸면 출력 차원도 따라 바뀐다.
    """
    config_type: str = _PROFILE_STATS_CFG
    object_type: str = _PROFILE_STATS_NAME
    trainable: bool = False
    length: int = 512
    quantiles: tuple[float, ...] = _QUANTILES


@MODELS.Register_module(_PROFILE_STATS_NAME)
class Profile_Stats(Trainable_Model):
    """``(B, N)`` 프로파일 -> ``(B, 10)`` 통계.

    Args:
        length: 프로파일 길이 ``N``. 백분위 인덱스를 상수로 굳히기 위해 필요하다.
        quantiles: 백분위 목록. 개수를 바꾸면 출력 차원도 따라 바뀐다.
    """

    _lo: Tensor
    _hi: Tensor
    _w: Tensor

    def Out_channels(self) -> list[int]:
        return [self.dim]

    def Build(
        self, length: int = 512, quantiles: tuple[float, ...] = _QUANTILES, **kwargs: Any
    ) -> None:
        self.length = int(length)
        self.quantiles = tuple(float(_q) for _q in quantiles)

        _pos = torch.tensor(self.quantiles, dtype=torch.float64) * (self.length - 1)
        _lo = _pos.floor()
        self.register_buffer("_lo", _lo.to(torch.long), persistent=False)
        self.register_buffer("_hi", _pos.ceil().to(torch.long), persistent=False)
        self.register_buffer("_w", (_pos - _lo).to(torch.float32), persistent=False)

    @property
    def dim(self) -> int:
        """mean/std/min/max/range 5개 + 백분위 개수."""
        return 5 + len(self.quantiles)

    def Spec(self, name: str, vmax: float) -> tuple[Feature_Spec, ...]:
        """Args: name: 그룹 이름. vmax: 원본 프로파일의 이론 상한(예: r_max).

        **원본 스케일(선형)** — 형상 통계라 log 로 뭉개지 않는다.
        """
        return (Feature_Spec(name, self.dim, "identity", (0.0, vmax)),)

    def forward(self, profile: Tensor) -> Tensor:
        """
        Args:
            profile: (B, N) float.

        Returns:
            (B, 5 + len(quantiles)) float — mean/std/min/max/range 뒤에 백분위.
        """
        _srt, _ = profile.sort(dim=-1)
        _lo = _srt.index_select(-1, self._lo)
        _hi = _srt.index_select(-1, self._hi)
        _q = _lo * (1.0 - self._w) + _hi * self._w                 # (B, 5)

        _min = _srt[..., :1]
        _max = _srt[..., -1:]
        return torch.cat(
            [
                profile.mean(dim=-1, keepdim=True),
                profile.std(dim=-1, unbiased=False, keepdim=True),
                _min, _max, _max - _min, _q,
            ],
            dim=-1,
        )
