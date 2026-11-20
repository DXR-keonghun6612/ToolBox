"""torch runner - GPU 한 장에서 실제로 도는 흐름. 학습 -> 이어서 학습 -> 고른 체크포인트로 test -> ONNX export, 이른 멈춤, 실패 기록.

입력 `tests/resource/gpu/`
- `hub.yaml` : `project_name: toy`, `job: learning`, `max_iters: 3`, `shared.classes`, `mode` 의 train / val / test(합성 데이터셋, scalar 지표)
- `model.yaml` : `toy_model_Config`(in_dim 4, classes `${shared.classes}`) - `model` 아래
- `loss.yaml` : `logits` 에 cross entropy - `loss` 아래
- `optim.yaml` : SGD - `optim` 아래

합성 데이터셋, 모델, job, runner 는 `tests/support/toy.py`. 결과 자리는 케이스마다 빈 폴더(`tmp_path`). GPU 가 없으면 건너뜀.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime
import pytest
import torch

from python_toolbox.run import runner as runner_module
from python_toolbox.run.log import CONSOLE, Log_Config, Setup_log
from support.toy import BEST, Base_argv, Toy_Runner

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")


def _Events(result_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (result_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_gpu_runner_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "RESULT_ROOT", str(tmp_path))
    _base = Base_argv()

    # step : learning - iterations, checkpoints, metric json, metric records, saved config
    _first = Toy_Runner.From_argv(_base)
    assert _first.config.model.classes == 3, "learning: shared value into the model"
    assert _first.Run() is True, "learning: finished without error records"
    _dir = _first.result_dir
    assert sorted(_p.name for _p in (_dir / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt", "checkpoint_1.pt", "checkpoint_2.pt"], "learning: checkpoint per iteration"
    assert (_dir / "avg" / "val" / "scalar" / "iter_2.json").is_file(), "learning: val metric json"
    _metric = [_e for _e in _Events(_dir) if _e["name"] == "metric"]
    assert len(_metric) == 3 and "val/accuracy" in _metric[-1] and "train/loss" in _metric[-1], \
        "learning: one metric record per iteration with mode/name keys"
    assert (_dir / "config.yaml").is_file(), "learning: config saved"

    # step : resume learning - continues from the last checkpoint up to the new max
    _resume = f"resume={_dir}"
    _more = Toy_Runner.From_argv([*_base, _resume, "max_iters=5"])
    assert _more.Run() is True and (_dir / "checkpoints" / "checkpoint_4.pt").is_file(), \
        "resume: continued to the new max"
    _iters = [_e["iter"] for _e in _Events(_dir) if _e["name"] == "metric"]
    assert _iters[-2:] == [3, 4], f"resume: started after the last checkpoint {_iters}"
    with pytest.raises(ValueError):
        Toy_Runner.From_argv([*_base, _resume, "optim.base_lr=0.5"])

    # step : test - one pass on the test mode with the best val checkpoint
    _best = BEST(_dir)
    _test = Toy_Runner.From_argv([*_base, _resume, "test=true"])
    assert _test.Run() is True, "test: finished"
    assert (_dir / "avg" / "test" / "scalar" / f"iter_{_best}.json").is_file(), "test: metric of the picked iteration"

    # step : export - onnx and runtime config in the run dir, the onnx runs
    _export = Toy_Runner.From_argv([*_base, _resume, "job=export", "export.precision=FP16", "export.opset_version=17"])
    assert _export.Run() is True, "export: finished"
    assert (_dir / "toy.onnx").is_file() and (_dir / "toy_rt_cfg.yaml").is_file(), "export: onnx and runtime config"
    _session = onnxruntime.InferenceSession(str(_dir / "toy.onnx"), providers=["CPUExecutionProvider"])
    _out = _session.run(None, {"x": np.zeros((1, 4), dtype=np.float32)})[0]
    assert _out.shape == (1, 3), "export: onnx gives logits for 3 classes"

    # step : early stop - one iteration, still a success
    _early = Toy_Runner.From_argv([*_base, "job=early"])
    assert _early.Run() is True, "early: stop is not a failure"
    assert sorted(_p.name for _p in (_early.result_dir / "checkpoints").iterdir()) == ["checkpoint_0.pt"], \
        "early: stopped after the first iteration"

    # step : broken forward - logged with a trace, run fails
    _broken = Toy_Runner.From_argv([*_base, "job=broken"])
    assert _broken.Run() is False, "broken: run failed"
    _errors = [_e for _e in _Events(_broken.result_dir) if _e["level"] == "ERROR"]
    assert _errors and "forward broke" in _errors[0]["exc"], "broken: error record with the trace"

    Setup_log(None, {"root": Log_Config(level="WARNING", to=[CONSOLE])})
