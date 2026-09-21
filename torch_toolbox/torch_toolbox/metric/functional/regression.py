"""연속 오차의 threshold-sweep 정확도, AUC."""
from __future__ import annotations

import torch
from torch import Tensor


def Get_accs(
    errors: Tensor,
    max_threshold: float,
    step_ct: int,
    mask: Tensor | None = None,
) -> tuple[Tensor, Tensor]:
    """정확도 곡선. threshold t 마다 `errors <= t` 비율.

    Args:
        errors: (N,) 오차.
        max_threshold: threshold 상한. 0 부터 선형 분할.
        step_ct: 분할 수. 포인트 수 step_ct + 1.
        mask: (N,) bool / float. None 이면 전체.

    Returns:
        (acc_curve (step_ct + 1,), thresholds (step_ct + 1,)).
    """
    _ths = torch.linspace(0, max_threshold, step_ct + 1, device=errors.device)
    _acc_curve = torch.stack([
        ((errors <= _t) if mask is None else (errors <= _t) * mask).float().mean()
        for _t in _ths
    ])
    return _acc_curve, _ths


def Compute_auc(
    errors_list: list[Tensor],
    max_thresholds: list[float],
    step_ct: int,
    mask: Tensor | None = None,
) -> tuple[Tensor, list[Tensor]]:
    """복수 오차의 결합 AUC. 곡선은 포인트별 최솟값으로 병합, 사다리꼴 적분. threshold 축은 첫 오차 기준.

    Args:
        errors_list: 오차 Tensor 목록. `max_thresholds` 와 같은 길이.
        max_thresholds: 오차별 threshold 상한.
        step_ct: 분할 수.
        mask: 유효 샘플 마스크. None 이면 전체.

    Returns:
        (병합 AUC (정규화), 오차별 AUC 목록).
    """
    assert len(errors_list) == len(max_thresholds), "errors_list와 max_thresholds 길이 불일치"

    _auc_per_error: list[Tensor] = []

    _base_e, _base_th = errors_list[0], max_thresholds[0]
    _merged, _ths = Get_accs(_base_e, _base_th, step_ct, mask)
    _auc_per_error.append(torch.trapz(_merged, _ths) / _base_th)

    for _e, _th in zip(errors_list[1:], max_thresholds[1:]):
        _curve, _ = Get_accs(_e, _th, step_ct, mask)
        _auc_per_error.append(torch.trapz(_curve, _ths) / _base_th)
        _merged = torch.minimum(_merged, _curve)

    return torch.trapz(_merged, _ths) / _base_th, _auc_per_error
