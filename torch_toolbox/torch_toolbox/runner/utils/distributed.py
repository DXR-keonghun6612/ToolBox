import torch
import torch.distributed as dist


def Reduce_metrics(
    metrics: dict[str, float], device: torch.device, world_size: int
) -> dict[str, float]:
    """전 rank 평균 (all_reduce, 모든 rank 가 같은 시점에 호출). 단일 GPU 나 분산 미초기화면 float 변환만."""
    if world_size <= 1 or not dist.is_initialized() or not metrics:
        return {k: float(v) for k, v in metrics.items()}

    _keys = list(metrics.keys())
    _values = []

    for k in _keys:
        v = metrics[k]
        if isinstance(v, (int, float)):
            _values.append(float(v))
        elif isinstance(v, torch.Tensor):
            _values.append(v.detach().item())
        else:
            raise ValueError(
                f"[ERROR] 지원하지 않는 메트릭 타입: {type(v)} for key {k}"
            )

    _tensor = torch.tensor(_values, dtype=torch.float32, device=device)
    dist.all_reduce(_tensor, op=dist.ReduceOp.SUM)
    _tensor /= world_size

    return {k: v for k, v in zip(_keys, _tensor.cpu().tolist())}
