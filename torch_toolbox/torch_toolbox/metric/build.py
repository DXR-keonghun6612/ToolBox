from __future__ import annotations

from . import ACCUMULATORS
from .definition import Accumulator_Config, Assemble_Metric_Config, Assemble_Metric


def Build_metric(cfg: Assemble_Metric_Config) -> Assemble_Metric:
    """`sub_metric_meta` 의 항목마다 `ACCUMULATORS` 에서 Accumulator 생성."""
    _accs = {}
    for _name, _meta in cfg.sub_metric_meta.items():
        _acc_cfg = Accumulator_Config(**_meta)
        _accs[_name] = ACCUMULATORS.Get(_acc_cfg.object_type)(**_acc_cfg.Extract())
    return Assemble_Metric(_accs)
