"""torch launcher - GPU 한 장에서 실제로 도는 흐름. 학습 -> 이어서 학습 -> 고른 체크포인트로 test -> ONNX export, 이른 멈춤, 실패 기록.

입력 `tests/resource/gpu/`
- `learning_launcher.yaml` : `project_name: toy`, `meta.learning: file@./learning.yaml`
- `learning.yaml` : `supervised_Config`, `object_type: learning`, `max_iters: 3`, job 기록 JSON, `model` / `loss` / `optim` 은 `file@`,
  `mode` 의 train / val / test(합성 데이터셋, scalar 지표, classes 는 `${learning.model.classes}`)
- `model.yaml` : `toy_model_Config`(in_dim 4, classes 3), `loss.yaml` : `logits` 에 cross entropy, `optim.yaml` : SGD
- `export_launcher.yaml` : `meta.export`(`export_job_Config`, FP16, opset 17) - `export.source` 는 argv 로

합성 데이터셋, 모델, job, launcher 는 `tests/support/toy.py`. 바탕 자리는 케이스마다 빈 폴더(`tmp_path`). GPU 가 없으면 건너뜀.
기록은 바탕 자리의 `log/` 하나에 실행마다 이어 씀. 체크포인트, 지표 json, export 산출물은 job 마다의 run 폴더.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime
import pytest
import torch

from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.launcher import LAUNCHER_LOGGER
from python_toolbox.run.log import LOG_DIR, Detach
from support.toy import BEST, EXPORT, LEARNING, Toy_Launcher

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")


def _Events(base_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (base_dir / LOG_DIR / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def _New_run_dir(base_dir: Path, before: set[Path]) -> Path:
    """이번 `Run` 이 만든 run 폴더 하나."""
    _new = [_p for _p in base_dir.iterdir() if _p.name != LOG_DIR and _p not in before]
    assert len(_new) == 1, f"one new run dir expected, got {_new}"
    return _new[0]


def test_gpu_launcher_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path))

    # step : learning - iterations, checkpoints and metric json in the run dir, metric records in the log dir
    _first = Toy_Launcher.From_argv([LEARNING])
    _base = _first.base_dir
    assert _first.space.Get("learning.mode.train.loader.dataset_meta.data_kwargs.classes") == 3, \
        "learning: model value into the dataset through reference"
    assert _first.Run()["learning"][0] == 0, "learning: finished without error records"
    _dir = _New_run_dir(_base, set())
    assert sorted(_p.name for _p in (_dir / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt", "checkpoint_1.pt", "checkpoint_2.pt"], "learning: checkpoint per iteration"
    assert (_dir / "avg" / "val" / "scalar" / "iter_2.json").is_file(), "learning: val metric json"
    _metric = [_e for _e in _Events(_base) if _e["name"] == "job.learning.metric"]
    assert len(_metric) == 3 and "val/accuracy" in _metric[-1] and "train/loss" in _metric[-1], \
        "learning: one metric record per iteration with mode/name keys"

    # step : resume learning - continues from the last checkpoint up to the new max
    _resume = f"learning.resume={_dir}"
    _more = Toy_Launcher.From_argv([LEARNING, _resume, "learning.max_iters=5"])
    assert _more.Run()["learning"][0] == 0 and (_dir / "checkpoints" / "checkpoint_4.pt").is_file(), \
        "resume: continued to the new max"
    _iters = [_e["iter"] for _e in _Events(_base) if _e["name"] == "job.learning.metric"]
    assert _iters[-2:] == [3, 4], f"resume: started after the last checkpoint {_iters}"

    # step : test - one pass on the test mode with the best val checkpoint
    _best = BEST(_dir)
    _test = Toy_Launcher.From_argv([LEARNING, _resume, "learning.test=true"])
    assert _test.Run()["learning"][0] == 0, "test: finished"
    assert (_dir / "avg" / "test" / "scalar" / f"iter_{_best}.json").is_file(), "test: metric of the picked iteration"

    # step : export - onnx and runtime config in the export's own run dir, read from the finished run, the onnx runs
    _before = set(_base.iterdir())
    _export = Toy_Launcher.From_argv([EXPORT, f"export.source={_dir}"])
    assert _export.Run()["export"][0] == 0, "export: finished"
    _out_dir = _New_run_dir(_base, _before)
    assert (_out_dir / "toy.onnx").is_file() and (_out_dir / "toy_rt_cfg.yaml").is_file(), \
        "export: onnx and runtime config"
    _session = onnxruntime.InferenceSession(str(_out_dir / "toy.onnx"), providers=["CPUExecutionProvider"])
    _out = _session.run(None, {"x": np.zeros((1, 4), dtype=np.float32)})[0]
    assert _out.shape == (1, 3), "export: onnx gives logits for 3 classes"

    # step : early stop - one iteration, still a success
    _before = set(_base.iterdir())
    _early = Toy_Launcher.From_argv([LEARNING, "learning.object_type=early"])
    assert _early.Run()["learning"][0] == 0, "early: stop is not a failure"
    assert sorted(_p.name for _p in (_New_run_dir(_base, _before) / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt"], "early: stopped after the first iteration"

    # step : broken forward - logged with a trace, job fails
    _broken = Toy_Launcher.From_argv([LEARNING, "learning.object_type=broken"])
    assert _broken.Run()["learning"][0] == 1, "broken: job failed"
    _errors = [_e for _e in _Events(_base) if _e["level"] == "ERROR" and "exc" in _e]
    assert _errors and "forward broke" in _errors[-1]["exc"], "broken: error record with the trace"

    Detach(LAUNCHER_LOGGER)
