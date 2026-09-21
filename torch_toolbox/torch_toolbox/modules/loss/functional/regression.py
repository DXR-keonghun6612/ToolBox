import torch

def relative_error_by_dot(
    predict: torch.Tensor,
    target: torch.Tensor,
    alpha: float = 1.0
) -> torch.Tensor:
    """두 벡터 사이 각도 (정규화 후 내적의 acos).

    Args:
        predict: (..., D) 예측 벡터.
        target: (..., D) 정답 벡터.
        alpha: 결과에 곱하는 배율.

    Returns:
        (...,) radian.
    """
    _pre = predict / (predict.norm(dim=-1, keepdim=True) + 1e-8)
    _tgt = target / (target.norm(dim=-1, keepdim=True) + 1e-8)
    _dot = torch.sum(_pre * _tgt, dim=-1).abs().clamp(min = 0.0, max=1.0)
    return alpha * torch.acos(_dot)

def relative_error_by_mse(
    predict: torch.Tensor,
    target: torch.Tensor
) -> torch.Tensor:
    """(..., 3) 병진 벡터 차의 L2 norm -> (...,)."""
    _diff = predict - target
    return torch.norm(_diff, dim=-1)

def relative_rotation_from_matrix(
    predict: torch.Tensor,
    target: torch.Tensor
) -> torch.Tensor:
    """(N, 3, 3) 회전 행렬 사이 각도 -> (N,) radian."""
    _diff = torch.matmul(predict.transpose(-2, -1), target)
    _trace = _diff[:, 0, 0] + _diff[:, 1, 1] + _diff[:, 2, 2]
    _theta = ((_trace - 1) / 2).clamp(-1, 1)
    return torch.acos(_theta)
