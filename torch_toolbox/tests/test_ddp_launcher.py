"""torch runner - GPU 둘에서 DDP 로 도는 흐름. 학습 -> 이어서 학습, rank 0 이 정한 이른 멈춤, 자식 프로세스의 실패.

입력 `tests/resource/gpu/` - `test_gpu_runner.py` 와 같음, argv 로 `gpus=[0,1]`, `world_size=2`, 빈 port.
합성 학습은 `tests/support/toy.py` - DDP 자식이 그 모듈에서 job 클래스를 다시 import. GPU 가 둘보다 적으면 건너뜀.
기록은 결과 자리의 `log/` 하나에 실행마다 이어 씀. 체크포인트는 job 의 run 폴더 - 자식은 부모의 run 폴더를 받음.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
import torch

from python_toolbox.run import runner as runner_module
from python_toolbox.run.log import CONSOLE, Log_Config, Setup_log
from python_toolbox.run.runner import LOG_DIR
from support.toy import Base_argv, Toy_Runner

pytestmark = pytest.mark.skipif(torch.cuda.device_count() < 2, reason="needs two CUDA GPUs")


def _Free_port() -> int:
    with socket.socket() as _s:
        _s.bind(("localhost", 0))
        return _s.getsockname()[1]


def _Events(result_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (result_dir / LOG_DIR / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def _Ddp() -> list[str]:
    return ["gpus=[0,1]", "world_size=2", f"port_num={_Free_port()}"]


def test_ddp_runner_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "RESULT_ROOT", str(tmp_path))
    _base = Base_argv()

    # step : learning on two processes - rank 0 saves checkpoints into the parent's run dir and writes the records
    _first = Toy_Runner.From_argv([*_base, *_Ddp()])
    assert _first.job.is_multi_gpu, "ddp: two gpus"
    assert _first.Run() is True, "ddp learning: finished"
    _dir = _first.job.run_dir
    assert sorted(_p.name for _p in (_dir / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt", "checkpoint_1.pt", "checkpoint_2.pt"], "ddp learning: checkpoint per iteration"
    _events = _Events(_first.result_dir)
    assert len([_e for _e in _events if _e["name"] == "metric"]) == 3, "ddp learning: one metric record per iteration"
    assert any(_e.get("rank") == 0 for _e in _events), "ddp learning: rank 0 child records reach the run log"

    # step : resume on two processes
    _more = Toy_Runner.From_argv([*_base, *_Ddp(), f"job.resume={_dir}", "max_iters=4"])
    assert _more.Run() is True and (_dir / "checkpoints" / "checkpoint_3.pt").is_file(), "ddp resume: continued"

    # step : early stop decided by rank 0 and broadcast - every process stops after one iteration
    _early = Toy_Runner.From_argv([*_base, *_Ddp(), "job.object_type=early"])
    assert _early.Run() is True, "ddp early: stop is not a failure"
    assert sorted(_p.name for _p in (_early.job.run_dir / "checkpoints").iterdir()) == ["checkpoint_0.pt"], \
        "ddp early: stopped after the first iteration"

    # step : a child process fails - the exception reaches the parent, run fails
    _broken = Toy_Runner.From_argv([*_base, *_Ddp(), "job.object_type=broken"])
    assert _broken.Run() is False, "ddp broken: run failed"

    Setup_log(None, {"root": Log_Config(level="WARNING", to=[CONSOLE])})
