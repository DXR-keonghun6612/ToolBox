from __future__ import annotations

import torch
from torch import Tensor

"""theta 축 순환 정합 거리 — **정렬 품질 측정과 저신뢰 표본의 대비책**.

주 용도는 :func:`~torch_toolbox.modules.transform.functional.frame.Centroid_frame` 의 정렬이
얼마나 일관적인지 **재는 것**이다. 같은 마스크를 여러 각도로 돌려 정렬한 뒤 결과 프로파일의
최적 순환 shift 를 보면, shift 가 0 이 아닌 비율이 곧 정렬 실패율이다.

정렬 자체는 신뢰할 만하다 — 실데이터 1400 마스크 x 8 회전 기준 **99.79% 자기일관**, 실패는
전량 180° 이분법이다. 따라서 여기 있는 불변 거리는 정렬의 대체재가 아니라

    - 회귀 측정 도구 (정렬 방식을 바꿀 때 개선 여부를 수치로 확인)
    - ``flip_margin`` 이 낮은 소수 표본의 대비책

으로 쓴다. **정렬을 대체하면 절대 크기·위상 정보를 버리게 되므로** 기본 경로로 삼지 않는다.

순환 shift 군은 좌표 치환 = isometry 로 작용하므로 ``min_s ||x - roll(y, s)||`` 는 몫공간
위의 **진짜 metric** 이다 — 삼각부등식이 성립해 클러스터링·ANN 인덱스에 그대로 쓸 수 있다.

lag 집합이 무엇을 버리는지가 설계 선택이다:

    :func:`Flip_lags` 로 제한   : 180°(+지터)만 흡수. 회전 판별력 보존.
    전체 NT lag                 : 완전 회전 불변. 회전만 다른 형상은 거리 0 이 된다.

Note:
    같은 클래스 표본끼리의 불일치율은 정렬 실패율보다 훨씬 크게 나온다(실측 6%+ 대 0.2%).
    그 차이는 정렬이 아니라 **객체 분리 품질**에서 온다 — 이웃 조각이 붙거나 가려져 잘린
    마스크는 형상 자체가 다르다. 이 거리로 그 둘을 구분할 수는 없으니, 측정 결과를 정렬
    품질로 읽으려면 **같은 마스크를 회전시킨** 자기일관성 설정을 써야 한다.
"""


def Circular_correlation(a: Tensor, b: Tensor) -> Tensor:
    """theta 축 순환 상호상관. ``(B, NR, NT)`` x ``(M, NR, NT)`` -> ``(B, M, NT)``.

    ``out[..., s] = <a, roll(b, s, dim=-1)>`` (r 까지 합산).

    shift 는 r 전체가 공유하므로 **NR 합산을 주파수영역에서 먼저 접는다.** 이걸 안 하고
    lag 마다 차를 만들면 중간 텐서가 ``B·M·NR·NT`` 로 커진다 (64x64x224x512 fp32 ~= 3.7GB).
    접고 나면 ``B·M·K`` 복소수로 끝난다 (~8MB).
    """
    _nt = a.shape[-1]
    _fa = torch.fft.rfft(a.float(), dim=-1)                        # (B, NR, K)
    _fb = torch.fft.rfft(b.float(), dim=-1)                        # (M, NR, K)
    _c = torch.einsum("brk,mrk->bmk", _fa, _fb.conj())             # r 을 여기서 접는다
    return torch.fft.irfft(_c, n=_nt, dim=-1)                      # (B, M, NT)


def Flip_lags(num_angular: int, width: int = 0, device: torch.device | None = None) -> Tensor:
    """180° 모호성 + ``±width`` bin 지터만 훑는 lag 집합 -> ``(2*width+1) * 2``.

    PCA 는 각을 mod π 로 잡으므로, 두 샘플의 flip 이 각각 a·b 라면 상대 shift 는
    ``(a-b) mod 2`` — 즉 ``0`` 또는 ``NT/2`` 뿐이다. 후보 둘이면 충분하다.

    ``width`` 는 잔차 각도 지터용이다.
    :class:`~torch_toolbox.modules.transform.radial.Radial` 이 회전을
    ``round(angle / dtheta)`` 로 bin 양자화하고, ``anisotropy`` 가 낮은 샘플은 각 자체가
    흔들리므로 정확히 ``{0, NT/2}`` 가 아니라 그 근방을 봐야 한다.

    Note:
        ``NT`` 가 짝수여야 ``NT/2`` 가 정확한 정수 shift 가 된다.
    """
    if num_angular % 2 != 0:
        raise ValueError(f"num_angular 는 짝수여야 180° 가 정확한 shift 다: {num_angular}")
    _w = torch.arange(-width, width + 1, device=device)
    return torch.cat([_w, _w + num_angular // 2]) % num_angular


def Circular_align_d2(a: Tensor, b: Tensor, lags: Tensor | None = None) -> Tensor:
    """순환 정합 제곱거리 행렬. ``(B, NR, NT)`` x ``(M, NR, NT)`` -> ``(B, M)``.

    ``min_s ||a - roll(b, s)||²`` 을 ``lags`` 위에서 구한다. ``||a - roll(b,s)||² =
    ||a||² + ||b||² - 2·corr(s)`` 이므로 상관 최대점만 찾으면 된다.

    Args:
        a: (B, NR, NT) — theta 가 마지막 축.
        b: (M, NR, NT).
        lags: 훑을 shift 집합. ``None`` 이면 전체 ``NT`` (완전 회전 불변).
            180° 만 흡수하려면 :func:`Flip_lags` 를 넘긴다.

    Returns:
        (B, M) float — 제곱거리. 몫공간 위의 metric 이라 삼각부등식이 성립한다.
    """
    _corr = Circular_correlation(a, b)                             # (B, M, NT)
    if lags is not None:
        _corr = _corr.index_select(-1, lags.to(_corr.device))
    _ea = a.float().pow(2).sum(dim=(-2, -1)).unsqueeze(1)          # (B, 1)
    _eb = b.float().pow(2).sum(dim=(-2, -1)).unsqueeze(0)          # (1, M)
    return (_ea + _eb - 2.0 * _corr.amax(dim=-1)).clamp_min(0.0)   # 수치오차로 음수 방지

