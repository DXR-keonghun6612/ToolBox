from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any

import torch
from torch import Tensor
from torch.nn import functional as F

from .... import CFGS
from ... import MODELS
from ...definition import Composable_Config
from ...model.definition import Trainable_Model

from .canonical import Centroid_Frame

"""이미지 분기 — 실루엣 마스크 -> CNN 입력 채널. **모델의 첫 레이어**다.

데이터 증강과 다르다. 증강은 무작위이고 학습 전용이라 dataset 이 소유하지만, 여기 있는
것들은 **결정적이고 추론에도 똑같이 필요**하다. 그래서 모델에 속한다 — 그러면 학습·추론
동일성이 함수 공유가 아니라 **같은 그래프**로 보장되고 export 가 self-contained 가 된다.

정렬은 ``GridSample`` 을 쓰지 않는다. TRT 에서 GridSample 은 FP32/FP16 전용이라 INT8 을
옵션에서 지워버린다. 대신 수동 bilinear gather 로 짠다 — ``Polar_Raster._sample`` 에서
검증한 패턴과 같고, 인덱스가 상수가 아니라 런타임 텐서인 것만 다르다.
"""

_ALIGN_NAME = "align_raster"
_ALIGN_CFG  = f"{_ALIGN_NAME}_Config"
_CH_NAME    = "image_channels"
_CH_CFG     = f"{_CH_NAME}_Config"


@CFGS.Register_module(_ALIGN_CFG)
@dataclass
class Align_Raster_Config(Composable_Config):
    """주축 정렬 설정.

    Attributes:
        output_size: **출력** 캔버스 ``(H, W)``. 입력 캔버스는 ``forward`` 가 읽으므로 자유.
    """
    config_type: str = _ALIGN_CFG
    object_type: str = _ALIGN_NAME
    trainable: bool = False
    output_size: tuple[int, int] = (224, 224)


@MODELS.Register_module(_ALIGN_NAME)
class Align_Raster(Trainable_Model):
    """마스크를 :attr:`Frame.angle` 만큼 돌린다 — centroid 를 중심에, 주축을 수평으로.

    각도와 중심은 :class:`~torch_toolbox.modules.transform.mask.canonical.Centroid_Frame` 이
    해석적으로 준다 — 축은 k=2 harmonic, 180° 는 k=3 harmonic ``Z3`` 의 위상(부품별
    ``flip_phase_deg`` 표)이 정한 값이다. 여기서는 그 파라미터로 리샘플만 한다. 기존 numpy
    경로는 LINEAR resize 후 NEAREST warp 를 확장 캔버스에 걸고 다시 crop 해 **리샘플을 두 번**
    했다 — 여기서는 한 번이다.

    출력 캔버스는 ``output_size``, 입력 캔버스는 ``forward`` 가 읽으므로 자유다.

    Note:
        **"정준(canonical) 자세" 가 아니다.** 대칭 형상은 각도 자체가 미결정이다
        (n>=3 회전대칭이면 ``Z2 = 0``, 2회 대칭이면 ``Z3 = 0``) — 그 경우 여기 출력은
        노이즈가 정한 방향이다. :attr:`Frame.anisotropy` / :attr:`Frame.flip_margin` 이
        그 미결정성을 보고하므로 소비처가 함께 읽어야 한다.

        회전 자유도를 **제거**하는 쪽이다. 무작위로 흔들어 모델이 배우게 하는
        :class:`~dataloader.utils.augment.Mask_Rotate` 와 상호 배타적이며, 이쪽은
        추론에도 필요해 배포 그래프에 리샘플이 남는다.
    """

    _gx: Tensor
    _gy: Tensor

    def Build(self, output_size: tuple[int, int] = (224, 224), **kwargs: Any) -> None:
        _h, _w = int(output_size[0]), int(output_size[1])
        self.output_size = (_h, _w)
        # 길이 단위 상수는 출력 캔버스 반대각. 여기서는 FP16 무차원화에만 쓰임
        _radius = int(math.ceil(math.hypot((_h - 1) / 2.0, (_w - 1) / 2.0)))
        self.frame = Centroid_Frame(name="frame", trainable=False, trust_radius=_radius)

        # 출력 픽셀의 캔버스 중심 기준 좌표 (상수).
        _ys = torch.arange(_h, dtype=torch.float32) - (_h - 1) / 2.0
        _xs = torch.arange(_w, dtype=torch.float32) - (_w - 1) / 2.0
        _gy, _gx = torch.meshgrid(_ys, _xs, indexing="ij")
        self.register_buffer("_gx", _gx.reshape(1, -1), persistent=False)
        self.register_buffer("_gy", _gy.reshape(1, -1), persistent=False)

    def Out_channels(self) -> list[int]:
        """정렬만 하므로 채널 수는 그대로 1."""
        return [1]

    def forward(self, mask: Tensor) -> Tensor:
        """
        Args:
            mask: (B, 1, Hin, Win) float — 전경 1 / 배경 0. 입력 캔버스는 자유.

        Returns:
            (B, 1, H, W) float — 정준 자세. 캔버스는 ``output_size``.
        """
        _b = mask.shape[0]
        _h, _w = self.output_size                                     # 출력 캔버스
        _ih, _iw = mask.shape[-2], mask.shape[-1]              # 입력 캔버스 (gather 범위)
        _flat = mask.reshape(_b, -1)
        _frame = self.frame(mask)

        # 출력 좌표를 주축각만큼 돌려 입력 좌표로. centroid 를 캔버스 중심으로 옮긴다.
        _cos = torch.cos(_frame.angle).view(-1, 1)
        _sin = torch.sin(_frame.angle).view(-1, 1)
        _x = self._gx * _cos - self._gy * _sin + _frame.center[:, 0:1]
        _y = self._gx * _sin + self._gy * _cos + _frame.center[:, 1:2]

        _x0, _y0 = torch.floor(_x), torch.floor(_y)
        _fx, _fy = _x - _x0, _y - _y0
        _x0, _y0 = _x0.long(), _y0.long()

        def _tap(_dy: int, _dx: int) -> Tensor:
            _r, _c = _y0 + _dy, _x0 + _dx
            _ok = (_r >= 0) & (_r < _ih) & (_c >= 0) & (_c < _iw)
            _i = _r.clamp(0, _ih - 1) * _iw + _c.clamp(0, _iw - 1)
            return _flat.gather(1, _i) * _ok.to(_flat.dtype)

        _v = (
            _tap(0, 0) * ((1 - _fy) * (1 - _fx))
            + _tap(0, 1) * ((1 - _fy) * _fx)
            + _tap(1, 0) * (_fy * (1 - _fx))
            + _tap(1, 1) * (_fy * _fx)
        )
        return _v.view(_b, 1, _h, _w)


@CFGS.Register_module(_CH_CFG)
@dataclass
class Image_Channels_Config(Composable_Config):
    """CNN 입력 채널 구성.

    Attributes:
        channels: 쌓을 채널 이름 순서. ``mask`` / ``blur{k}`` / ``edge``.
        edge_kernel: edge 채널의 구조요소 크기(홀수).
    """
    config_type: str = _CH_CFG
    object_type: str = _CH_NAME
    trainable: bool = False
    channels: tuple[str, ...] = ("mask", "blur9", "blur25")
    edge_kernel: int = 3


@MODELS.Register_module(_CH_NAME)
class Image_Channels(Trainable_Model):
    """마스크 -> ``(B, C, H, W)`` 채널 스택. 전부 텐서 연산이다.

    채널 종류::

        mask     이진 원본 {0, 1}
        blur{k}  커널 k 박스 평활 [0, 1] — ``avg_pool2d``. 창 안 전경 비율이 곧 그 자리의
                 국소 **두께**라, 얇은 슬릿과 두꺼운 몸통이 값으로 갈린다.
                 (실측 224 캔버스: 전경 두께 중앙 22px / 구멍 폭 중앙 15px, p5 는 2.8/2.0px)
        edge     morphological gradient — ``maxpool - minpool``. 1픽셀 경계라 두께 정보가 없다.

    sdf 는 없다. ``cv2.distanceTransform`` 은 정확한 EDT 라 텐서 연산으로 안 펴졌고, 빼도
    val acc 가 두 구성 모두 0.994 이상이라 측정된 손해가 없었다. ``blur{k}`` 가 그 역할
    (경계 근처의 매끄러운 기울기장)을 훨씬 싸게 대신하면서 국소 두께까지 담는다.
    """

    def Build(
        self,
        channels: tuple[str, ...] = ("mask", "blur9", "blur25"),
        edge_kernel: int = 3,
        **kwargs: Any,
    ) -> None:
        self.channels = tuple(channels)
        self.edge_kernel = int(edge_kernel)
        for _c in self.channels:
            if _c not in ("mask", "edge") and not _c.startswith("blur"):
                raise ValueError(
                    f"알 수 없는 채널 이름: {_c!r} (가능: mask / blur{{k}} / edge)")

    def Out_channels(self) -> list[int]:
        """백본 ``in_chans`` 가 이 값을 받는다 — 채널을 바꾸면 자동으로 따라온다."""
        return [len(self.channels)]

    def forward(self, mask: Tensor) -> Tensor:
        """
        Args:
            mask: (B, 1, H, W) float — 전경 1 / 배경 0.

        Returns:
            (B, len(channels), H, W) float.
        """
        _out: list[Tensor] = []
        for _c in self.channels:
            if _c == "mask":
                _out.append(mask)
            elif _c.startswith("blur"):
                _k = int(_c[4:])
                _out.append(F.avg_pool2d(mask, _k, stride=1, padding=_k // 2))
            else:
                _k = self.edge_kernel
                _dil = F.max_pool2d(mask, _k, stride=1, padding=_k // 2)
                _ero = -F.max_pool2d(-mask, _k, stride=1, padding=_k // 2)
                _out.append(_dil - _ero)
        return torch.cat(_out, dim=1)
