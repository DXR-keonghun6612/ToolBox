from __future__ import annotations
from typing import Any
from pathlib import Path

from python_toolbox.file import Write_to
from python_toolbox.system import String

from ...metric.definition import Assemble_Metric


def log_batch(
    current_iter: int,
    batch_idx: int,
    total_batches: int,
    mode_accs: Assemble_Metric,
    key_list: list[str],
) -> None:
    """`key_list` 의 accumulator 현재 값을 progress bar 로."""
    _scalars: dict[str, float] = {}
    for _key in key_list:
        if _key in mode_accs:
            _scalars.update(mode_accs[_key].Finalize())
    if not _scalars:
        return
    _suffix = "  ".join(f"{_k}={_v:.4f}" for _k, _v in _scalars.items())
    String.Progress_bar(
        iteration=batch_idx + 1,
        total=total_batches,
        prefix=f"[iter {String.Count_auto_align(current_iter, 9999)}]",
        suffix=_suffix,
    )


def log_iter(
    iter_idx: int,
    results: dict[str, dict[str, Any]],
    workspace: Path,
) -> None:
    """mode 별 accumulator 결과를 터미널 + `workspace/avg/<mode>/<acc_name>/iter_<i>.json`."""
    _summary_parts: list[str] = []
    for _mode, _mode_results in results.items():
        for _acc_name, _data in _mode_results.items():
            if not isinstance(_data, dict) or not _data:
                continue
            _persist(iter_idx, _mode, _acc_name, _data, workspace)
            _summary_parts.extend(
                f"{_mode}/{_k}={_v:.6f}" for _k, _v in _data.items()
                if isinstance(_v, float)
            )
    if _summary_parts:
        print(f"[iter {iter_idx}] " + "  ".join(_summary_parts))


def _persist(
    iter_idx: int,
    mode: str,
    acc_name: str,
    data: dict[str, Any],
    workspace: Path,
) -> None:
    Write_to(workspace / "avg" / mode / acc_name / f"iter_{iter_idx}.json", data)
