"""학습 지표 기록 - 배치마다 진행 막대, iteration 마다 `metric` logger 한 줄과 `avg/<mode>/<acc_name>/iter_<i>.json`.

json 은 `Iter_Selection` 이 체크포인트를 고를 때 읽음.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from python_toolbox.file import Write_to
from python_toolbox.system import String

from ...metric.definition import Assemble_Metric

_metric_log = logging.getLogger("metric")


def log_batch(
    current_iter: int,
    batch_idx: int,
    total_batches: int,
    mode_accs: Assemble_Metric,
    key_list: list[str],
) -> None:
    """`key_list` 의 accumulator 지금 값을 진행 막대로."""
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
    run_dir: Path,
) -> None:
    """mode 별 accumulator 결과를 `metric` logger 한 줄(`extra` 에 `iter`, `<mode>/<지표>`)과 json 으로."""
    _values: dict[str, float] = {}
    for _mode, _mode_results in results.items():
        for _acc_name, _data in _mode_results.items():
            if not isinstance(_data, dict) or not _data:
                continue
            Write_to(run_dir / "avg" / _mode / _acc_name / f"iter_{iter_idx}.json", _data)
            _values.update({f"{_mode}/{_k}": _v for _k, _v in _data.items() if isinstance(_v, float)})
    if _values:
        _metric_log.info(
            f"iter {iter_idx} " + "  ".join(f"{_k}={_v:.6f}" for _k, _v in _values.items()),
            extra={"iter": iter_idx, **_values},
        )
