from __future__ import annotations

import torch
from torch import Tensor


def Top_k_accuracy(scores: Tensor, targets: Tensor, k: int = 1) -> float:
    """top-k 정확도.

    Args:
        scores: (N, C) 클래스별 점수. 열 index = 클래스 id.
        targets: (N,) 정답 클래스 id.
        k: 상위 후보 수.

    Returns:
        [0, 1].
    """
    _topk = scores.topk(k, dim=-1).indices            # (N, k)
    return (_topk == targets[:, None]).any(dim=1).float().mean().item()


def Confusion_matrix(preds: Tensor, targets: Tensor, num_classes: int) -> Tensor:
    """혼동 행렬. row = target, col = pred.

    Args:
        preds: (N,) 예측 클래스 id.
        targets: (N,) 정답 클래스 id.
        num_classes: C.

    Returns:
        (C, C) long. [i, j] = class i 를 j 로 예측한 수.
    """
    _idx = targets.long() * num_classes + preds.long()
    return torch.bincount(
        _idx, minlength=num_classes * num_classes
    ).reshape(num_classes, num_classes)
