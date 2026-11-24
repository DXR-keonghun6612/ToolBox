"""torch launcher - GPU 둘에서 DDP 로 도는 흐름. 학습 -> 이어서 학습, rank 0 이 정한 이른 멈춤, 자식 프로세스의 실패.

입력 `tests/resource/gpu/` - `test_gpu_launcher.py` 와 같음, argv 로 `learning.gpus=[0,1]`, `learning.world_size=2`, 빈 port.
합성 학습은 `tests/support/toy.py` - DDP 자식이 그 모듈에서 job 클래스를 다시 import. GPU 가 둘보다 적으면 건너뜀.
기록은 바탕 자리의 `log/` 하나에 실행마다 이어 씀. 체크포인트는 job 의 run 폴더 - 자식은 부모의 run 폴더를 받음.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
import torch

from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.job import FAILED
from python_toolbox.run.launcher import LAUNCHER_LOGGER
from python_toolbox.run.log import LOG_DIR, Detach
from support.toy import LEARNING, Toy_Launcher

pytestmark = pytest.mark.skipif(torch.cuda.device_count() < 2, reason="needs two CUDA GPUs")


def _Free_port() -> int:
    with socket.socket() as _s:
        _s.bind(("localhost", 0))
        return _s.getsockname()[1]


def _Events(base_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (base_dir / LOG_DIR / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def _New_run_dir(base_dir: Path, before: set[Path]) -> Path:
    """이번 `Run` 이 만든 run 폴더 하나."""
    _new = [_p for _p in base_dir.iterdir() if _p.name != LOG_DIR and _p not in before]
    assert len(_new) == 1, f"one new run dir expected, got {_new}"
    return _new[0]


def _Ddp() -> list[str]:
    return ["learning.gpus=[0,1]", "learning.world_size=2", f"learning.port_num={_Free_port()}"]


def test_ddp_launcher_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path))

    # step : learning on two processes - rank 0 saves checkpoints into the parent's run dir and writes the records
    _first = Toy_Launcher(LEARNING, _Ddp())
    _base = _first.base_dir
    assert _first.Run()["learning"][0] == 0, "ddp learning: finished"
    _dir = _New_run_dir(_base, set())
    assert sorted(_p.name for _p in (_dir / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt", "checkpoint_1.pt", "checkpoint_2.pt"], "ddp learning: checkpoint per iteration"
    _events = _Events(_base)
    assert len([_e for _e in _events if _e["name"] == "job.learning.metric"]) == 3, \
        "ddp learning: one metric record per iteration"
    assert any(_e.get("rank") == 0 for _e in _events), "ddp learning: rank 0 child records reach the log"

    # step : resume on two processes
    _more = Toy_Launcher(LEARNING, [*_Ddp(), f"learning.resume={_dir}", "learning.max_iters=4"])
    assert _more.Run()["learning"][0] == 0 and (_dir / "checkpoints" / "checkpoint_3.pt").is_file(), \
        "ddp resume: continued"

    # step : early stop decided by rank 0 and broadcast - every process stops after one iteration
    _before = set(_base.iterdir())
    _early = Toy_Launcher(LEARNING, [*_Ddp(), "learning.object_type=early"])
    assert _early.Run()["learning"][0] == 0, "ddp early: stop is not a failure"
    assert sorted(_p.name for _p in (_New_run_dir(_base, _before) / "checkpoints").iterdir()) == \
        ["checkpoint_0.pt"], "ddp early: stopped after the first iteration"

    # step : a child process fails - the exception reaches the parent, job fails
    _broken = Toy_Launcher(LEARNING, [*_Ddp(), "learning.object_type=broken"])
    assert _broken.Run()["learning"][0] == FAILED, "ddp broken: job failed"

    Detach(LAUNCHER_LOGGER)
