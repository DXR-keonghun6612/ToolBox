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

"""주기 프로파일의 Fourier 기술자 — **np.fft 없이 상수 기저 matmul 로**.

TensorRT 가 DFT 를 지원하지 않아 처음엔 FFT 를 빼야 하나 검토했으나, 질문이 잘못 놓여
있었다. 프로파일 길이 ``N`` 과 유지 harmonic 수 ``K`` 가 **설정으로 고정**이고 실제로 쓰는
것은 ``R[1..K]`` 뿐이다. N, K 가 상수면 DFT 는 그냥 **고정 선형사상**이다::

    re_k = sum_n p[n] * cos(2*pi*k*n/N)      k = 1..K
    im_k = -sum_n p[n] * sin(2*pi*k*n/N)

즉 ``(N, K)`` 상수 기저와의 matmul 하나. DFT 연산도 플러그인도 필요 없고, 차원이 120개
(426 중 28%) 걸린 기능을 그대로 살리면서 **수치가 같아 재학습이 필요 없다**.

위상 정규화: 저차 harmonic 중 dominant 한 ``k0`` 의 위상으로 기준각을 잡아 모든 harmonic 을
``exp(-i*k*phi0)`` 회전시킨다 -> 잔여 circular shift(회전)에 불변. magnitude 는 위상과
무관하므로 그대로 쓴다.

``k0`` 선택은 원본이 파이썬 ``if`` 였다. trace 하면 한쪽으로 굳으므로 ``torch.where`` 로
바꿨다 — 데이터 의존 분기를 그래프 안에 남기기 위한 필수 변경이다.
"""


_FOURIER_DESCRIPTOR_NAME = "fourier_descriptor"
_FOURIER_DESCRIPTOR_CFG  = f"{_FOURIER_DESCRIPTOR_NAME}_Config"


@CFGS.Register_module(_FOURIER_DESCRIPTOR_CFG)
@dataclass
class Fourier_Descriptor_Config(Composable_Config):
    """Fourier 기술자 설정.

    Attributes:
        length: 프로파일 길이 ``N``(= num_angular).
        num_harmonics: 유지할 harmonic 수 ``K``. ``N//2 - 1`` 로 상한이 걸린다.
        ref_max_k: 기준 harmonic ``k0`` 탐색 상한.
        ref_threshold: ``k0 = 1`` 로 볼 저차 에너지 비율 하한.
    """
    config_type: str = _FOURIER_DESCRIPTOR_CFG
    object_type: str = _FOURIER_DESCRIPTOR_NAME
    trainable: bool = False
    length: int = 512
    num_harmonics: int = 20
    ref_max_k: int = 8
    ref_threshold: float = 1.0e-3


@MODELS.Register_module(_FOURIER_DESCRIPTOR_NAME)
class Fourier_Descriptor(Trainable_Model):
    """``(B, N)`` 주기 프로파일 -> magnitude ``(B, K)`` + 위상보정 복소계수 ``(B, 2K)``.

    Args:
        length: 프로파일 길이 ``N``.
        num_harmonics: 유지할 harmonic 수 ``K``. ``N//2 - 1`` 로 상한이 걸린다.
        ref_max_k: 기준 harmonic ``k0`` 탐색 상한.
        ref_threshold: ``k0 = 1`` 로 볼 저차 에너지 비율 하한.
    """

    _cos: Tensor
    _sin: Tensor
    _ks: Tensor

    def Out_channels(self) -> list[int]:
        """magnitude K / phase 2K 두 텐서."""
        return [self.num_harmonics, 2 * self.num_harmonics]

    def Build(
        self,
        length: int = 512,
        num_harmonics: int = 20,
        ref_max_k: int = 8,
        ref_threshold: float = 1e-3,
        **kwargs: Any,
    ) -> None:
        self.length = int(length)
        self.num_harmonics = min(int(num_harmonics), self.length // 2 - 1)
        self.ref_max_k = min(int(ref_max_k), self.num_harmonics)
        self.ref_threshold = float(ref_threshold)

        _n = torch.arange(self.length, dtype=torch.float64)
        _k = torch.arange(1, self.num_harmonics + 1, dtype=torch.float64)
        _ang = 2.0 * math.pi * _k.view(1, -1) * _n.view(-1, 1) / self.length   # (N, K)
        self.register_buffer("_cos", torch.cos(_ang).to(torch.float32), persistent=False)
        self.register_buffer("_sin", torch.sin(_ang).to(torch.float32), persistent=False)
        self.register_buffer("_ks", _k.to(torch.float32).view(1, -1), persistent=False)

    @property
    def dim(self) -> int:
        """총 출력 차원 (magnitude K + 위상 2K)."""
        return 3 * self.num_harmonics

    def Spec(self, name: str, vmax: float) -> tuple[Feature_Spec, ...]:
        """magnitude 는 유계 비음수, phase 는 부호 있는 복소계수라 범위가 다르다.

        **원본 스케일(선형)** — 형상 스펙트럼이라 log 로 뭉개지 않는다.
        """
        return (
            Feature_Spec(f"{name}_fft_mag", self.num_harmonics, "identity", (0.0, vmax)),
            Feature_Spec(f"{name}_fft_phase", 2 * self.num_harmonics, "identity",
                         (-vmax, vmax)),
        )

    def forward(self, profile: Tensor) -> tuple[Tensor, Tensor]:
        """
        Args:
            profile: (B, N) float.

        Returns:
            ``(magnitude, phase)`` — ``(B, K)`` 와 ``(B, 2K)``. phase 는 실/허 인터리브.
        """
        _re = profile @ self._cos                                  # (B, K)
        _im = -(profile @ self._sin)
        _n = float(self.length)

        _abs = torch.sqrt(_re * _re + _im * _im)
        _mag = _abs / _n

        # k0 선택 — 원본의 파이썬 분기를 where 로. trace 되어도 데이터 의존이 유지된다.
        _low = _abs[:, : self.ref_max_k]
        _eng = _low.sum(dim=1, keepdim=True).clamp_min(torch.finfo(_abs.dtype).eps)
        _arg = _low.argmax(dim=1, keepdim=True) + 1                # (B, 1) 1-based
        _k0 = torch.where(_abs[:, :1] > self.ref_threshold * _eng,
                          torch.ones_like(_arg), _arg)             # (B, 1)

        _idx = _k0 - 1
        _phi0 = torch.atan2(_im.gather(1, _idx), _re.gather(1, _idx)) / _k0.to(_re.dtype)

        # Z_k = R_k * exp(-i*k*phi0) / N
        _kp = self._ks * _phi0                                     # (B, K)
        _c, _s = torch.cos(_kp), torch.sin(_kp)
        _zr = (_re * _c + _im * _s) / _n
        _zi = (_im * _c - _re * _s) / _n

        _phase = torch.stack([_zr, _zi], dim=2).reshape(_zr.shape[0], -1)
        return _mag, _phase
