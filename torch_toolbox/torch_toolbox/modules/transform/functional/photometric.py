"""RGB 광도 합성 연산. 게인, 오프셋, 저주파 조도 소거.

- 통계는 이미지 한 장의 공간 통계. 배치 결합 없음
- 저주파 추정은 `pool` 배 축소 격자에서. 창 한 변은 축소 격자 3칸 이상
"""
from __future__ import annotations

import torch
from torch import Tensor

from .color import Color_log_ratio, Luma, Saturation
from .filter import Sobel
from .pool import Local_stats, Weighted_lowpass, Weighted_mean


_RESIDUAL_SCALE_EPS = 1e-6   #: 평균 절대잔차 하한
_GRAD_EPS = 1e-6             #: 그래디언트 크기 제곱합 하한


def _Odd_kernel(window: float, pool: int) -> int:
    """원본 px 창 한 변 -> 축소 격자의 홀수 커널.

    Raises:
        ValueError: 창이 축소 격자 3칸 미만.
    """
    if window < 3 * pool:
        raise ValueError(f"창이 너무 작음: {window:.0f}px (최소 {3 * pool}px)")
    _k = round(window / pool)
    return _k if _k % 2 == 1 else _k + 1


def Illumination_normalize(
    x: Tensor,
    roi: Tensor | None,
    *,
    saturation_threshold: float,
    illum_window: int,
    illum_floor: float,
    flatten_strength: float,
    std_floor: float,
    pool: int,
    luma_weight: tuple[float, float, float],
) -> tuple[Tensor, Tensor]:
    """RGB -> 조명 적응 정규화 RGB + 포화 맵.

    순서 :
        1. 포화 맵 : raw 최대 채널의 `saturation_threshold` ~ 255 램프
        2. 조도 평탄화 : 포화 제외 휘도의 `illum_window` 규모 저주파로 나눔. roi 무관
        3. 채널별 정규화 : 포화, roi 밖을 뺀 가중 통계로 (x - mu_c) / sigma_c

    소거 : 절대 밝기, 색조, 창 규모 조도. 보존 : 상대 색차, 국소 대비.

    Args:
        x: (N, 3, H, W) RGB [0, 1]. 정규화 전 원본.
        roi: (N, 1, H, W) [0, 1]. 전역 통계를 낼 화소. None 이면 프레임 전체.
        saturation_threshold: 포화 램프 시작 (uint8 스케일, [0, 255)).
        illum_window: 조도 추정 정사각 창 한 변 (원본 px). 축소 격자에서 홀수 커널로 반올림.
        illum_floor: 조도 추정 하한 (휘도 스케일).
        flatten_strength: 평탄화 강도 [0, 1]. 0 = 평탄화 없음.
        std_floor: 채널 표준편차 하한.
        pool: 조도 추정 격자 축소 배수.
        luma_weight: 조도 추정 휘도 가중치.

    Returns:
        (정규화 RGB (N, 3, H, W), 포화 맵 (N, 1, H, W) [0, 1]).

    Raises:
        ValueError: 인자가 범위 밖.
    """
    if not 0.0 <= flatten_strength <= 1.0:
        raise ValueError(f"flatten_strength 는 [0, 1]: {flatten_strength}")
    _sat = Saturation(x, level=float(saturation_threshold) / 255.0)
    _w = 1.0 - _sat
    _stat_w = _w if roi is None else _w * roi

    if flatten_strength > 0.0:
        _kernel = _Odd_kernel(illum_window, pool)
        _luma = Luma(x, weight=luma_weight)
        _illum = Weighted_lowpass(_luma, _w, pool=pool, kernel=_kernel).clamp(min=illum_floor)
        # 게인 = roi 평균 조도 / 국소 조도
        x = x * (Weighted_mean(_luma, _stat_w) / _illum).pow(flatten_strength)

    _mu = Weighted_mean(x, _stat_w)
    _sigma = (Weighted_mean((x - _mu) ** 2, _stat_w) + std_floor ** 2).sqrt()
    return (x - _mu) / _sigma, _sat


def Surface_residual(
    x: Tensor,
    roi: Tensor | None,
    *,
    window_ratio: float,
    iters: int,
    cut: float,
    ratio_eps: float,
    pool: int,
    luma_weight: tuple[float, float, float],
) -> Tensor:
    """RGB -> 그 프레임의 배경면 저주파 대비 잔차. 출력에 roi 를 곱함.

    채널 [휘도, log(G/R), log(B/G)] 각각 L = box(v w) / box(w). w 는 roi 에서 시작해 잔차 |v - L| 이
    평균 절대잔차 s 의 `cut` 배를 넘는 화소를 1/(|r|/(cut s))^2 로 눌러 가며 `iters` 회 반복.
    가중은 채널마다 따로.

    Args:
        x: (N, 3, H, W) RGB [0, 1]. 정규화 전 원본.
        roi: (N, 1, H, W) [0, 1]. None 이면 프레임 전체.
        window_ratio: 정사각 창 한 변 / 입력 높이.
        iters: 잔차 가중 반복 횟수. 그래프에 펼침.
        cut: 가중 컷. 평균 절대잔차의 배수.
        ratio_eps: 색비 log 의 하한.
        pool: 저역 추정 격자 축소 배수.
        luma_weight: 휘도 가중치.

    Returns:
        (N, 3, H, W). roi * [휘도 - L, log(G/R) - L, log(B/G) - L].

    Raises:
        ValueError: 창이 축소 격자 3칸 미만.
    """
    _kernel = _Odd_kernel(window_ratio * float(x.shape[-2]), pool)
    _roi = x.new_ones(x[:, :1].shape) if roi is None else roi
    _v = torch.cat([Luma(x, weight=luma_weight), Color_log_ratio(x, eps=ratio_eps)], dim=1)

    _low = Weighted_lowpass(_v, _roi, pool=pool, kernel=_kernel)
    for _ in range(iters):
        _res = (_v - _low).abs()
        _s = Weighted_mean(_res, _roi).clamp(min=_RESIDUAL_SCALE_EPS)      # (N, 3, 1, 1)
        _w = _roi / (_res / (cut * _s)).clamp(min=1.0).pow(2)
        _low = Weighted_lowpass(_v, _w, pool=pool, kernel=_kernel)
    return (_v - _low) * _roi


def Local_contrast(
    x: Tensor,
    *,
    window: int,
    contrast_floor: float,
    luma_weight: tuple[float, float, float],
) -> Tensor:
    """정규화 RGB -> 색, 조명 불변 국소 대비.

    채널 [국소 정규화 휘도, 국소 정규화 그래디언트 크기]. 둘 다 같은 국소 표준편차로 나눔.
    크로마, 절대 휘도, 창보다 큰 영역의 정체성 없음. 창 안이 균일하면 0.

    Args:
        x: (N, 3, H, W). `Illumination_normalize` 출력.
        window: 국소 통계 창 한 변 (3 이상 홀수).
        contrast_floor: 국소 표준편차 하한. 정규화 입력 스케일.
        luma_weight: 휘도 가중치.

    Returns:
        (N, 2, H, W).

    Raises:
        ValueError: `window` 가 3 미만 또는 짝수.
    """
    if window % 2 == 0 or window < 3:
        raise ValueError(f"window 는 3 이상 홀수: {window}")
    _luma = Luma(x, weight=luma_weight)
    _mean, _scale = Local_stats(_luma, window=window, floor=contrast_floor)
    _mag = (Sobel(_luma)[:, 0].pow(2).sum(dim=1, keepdim=True) + _GRAD_EPS).sqrt()
    return torch.cat([(_luma - _mean) / _scale, _mag / _scale], dim=1)
