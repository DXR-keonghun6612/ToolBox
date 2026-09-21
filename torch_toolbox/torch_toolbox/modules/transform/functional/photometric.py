from __future__ import annotations

import torch
from torch import Tensor

from .color import Color_log_ratio, Luma, Saturation
from .filter import Sobel
from .pool import Local_stats, Weighted_lowpass, Weighted_mean

"""RGB 광도 합성 연산. 변환 모양이 알려진 변동(게인, 오프셋, 저주파 조도)만 지움.

- 통계는 이미지 한 장의 공간 통계. 배치 결합 없음 -> 배치 1 추론 = 학습
- 저주파 추정은 `pool` 배 축소 격자에서. 창 한 변은 축소 격자 3칸 이상
"""


_RESIDUAL_SCALE_EPS = 1e-6   #: 평균 절대잔차 하한. 잔차가 전부 0 일 때 0 나눗셈 방지
_GRAD_EPS = 1e-6             #: 그래디언트 크기 sqrt 안정화. sqrt(0) 미분 inf 방지


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
        2. 조도 평탄화 : 포화 제외 휘도의 `illum_window` 규모 저주파로 나눔 -> 공간 조도 차이
        3. 채널별 정규화 : 포화, roi 밖을 뺀 가중 통계로 (x - mu_c) / sigma_c -> 밝기, 색온도

    설계 :
        - 포화는 복원 불가. 통계에서 빼고 맵으로 따로 냄. clip 이 affine 가정을 깨고 sigma 를 오염시키는 것도 막음
        - 포화 맵은 raw 에서만. 정규화 뒤 255 는 이미지마다 다른 값
        - 전역 통계는 roi 로 제한. 프레임 전체면 배경 구성이 기준점을 정함
        - 조도 추정은 roi 무관. 조도는 프레임 어디에나 정의되고, roi 밖 가중합 0 이면 추정이 무너짐
        - 채널별 sigma. 색온도는 채널별 게인

    잃는 것 :
        - 절대 밝기, 색조. 상대 색차, 국소 대비는 보존
        - 창 규모 영역의 밝기 정체성. 창을 객체보다 충분히 크게 둬 완화
        - 창 안 객체 비중만큼 조도 추정이 끌려감 -> 객체 주변 완만한 halo

    Args:
        x: (N, 3, H, W) RGB [0, 1]. 정규화 전 원본.
        roi: (N, 1, H, W) [0, 1]. 전역 통계를 낼 화소. None 이면 프레임 전체.
        saturation_threshold: 포화 램프 시작 (uint8 스케일, [0, 255)).
        illum_window: 조도 추정 정사각 창 한 변 (원본 px). 축소 격자에서 홀수 커널로 반올림.
        illum_floor: 조도 추정 하한 (휘도 스케일). 어두운 영역의 게인 폭주 방지.
        flatten_strength: 평탄화 강도 [0, 1]. 0 = 평탄화 없음.
        std_floor: 채널 표준편차 하한. 평탄 프레임 노이즈 증폭 방지.
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
        # 게인 = roi 평균 조도 / 국소 조도. 전체 밝기는 3단계 몫이라 공간 분포만 폄
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
    """RGB -> 배경면 저주파 대비 잔차. 배경 이미지 없이 그 프레임 하나에서 면 모델을 세움.

    채널 [휘도, log(G/R), log(B/G)] 각각 L = box(v w) / box(w). w 는 roi 에서 시작해 잔차 |v - L| 이
    평균 절대잔차 s 의 `cut` 배를 넘는 화소를 1/(|r|/(cut s))^2 로 눌러 가며 `iters` 회 반복.

    - 면 = 0 인 절대 단서. 색비 잔차는 그림자에 불변, 무채색 객체는 이탈
    - 도메인 차이를 지우지 않음. 창보다 작은 면 구조(텍스처)는 잔차에 남음
    - 객체가 roi 에서 작은 비중이고 창이 객체보다 커야 평균이 객체에 안 끌림
    - 출력에 roi 를 곱함. roi 경계가 입력 엣지가 됨

    Args:
        x: (N, 3, H, W) RGB [0, 1]. 정규화 전 원본.
        roi: (N, 1, H, W) [0, 1]. None 이면 프레임 전체.
        window_ratio: 정사각 창 한 변 / 입력 높이. 해상도가 바뀌어도 객체 대비 창 비 유지.
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

    # 채널마다 따로 가중. 휘도에서 튀는 화소와 색비에서 튀는 화소가 다름
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

    채널 [국소 정규화 휘도, 국소 정규화 그래디언트 크기]. 둘 다 같은 국소 표준편차로 나눔 ->
    곱셈적 조도가 두 채널에서 함께 소거.

    - 크로마, 절대 휘도 없음. "이 색, 이 밝기 = 전경" 지름길 차단
    - 그림자, 반사광의 저주파 조도 변동은 국소 평균, 표준편차에 흡수 -> 반사율 경계만 남음
    - 그래디언트도 국소 표준편차로 나눔 -> 경계 강도가 대비에 무관
    - 창보다 큰 영역의 정체성은 사라짐. 창 안이 균일하면 0
    - 정반사 하이라이트는 급격한 경계라 채널 2 에 물체 윤곽과 구분 없이 남음

    Args:
        x: (N, 3, H, W). `Illumination_normalize` 출력.
        window: 국소 통계 창 한 변 (3 이상 홀수). 보존할 구조보다 충분히 크게.
        contrast_floor: 국소 표준편차 하한. 평탄 영역 노이즈 증폭 방지. 정규화 입력 스케일.
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
