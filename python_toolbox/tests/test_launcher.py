"""Launcher - launcher 설정 파일로 자기 설정과 meta 를 만들고, `Run` 때 meta 의 job 마다 설정을 지어 자기 프로세스로 띄우고, 결과를 자기 기록에 남김.

입력 `tests/resource/launcher/`
- `launcher.yaml` : `project_name`, `log`(`DEBUG`, JSON 출력 `events.jsonl` 하나), `meta.train`(`file@./train.yaml`), `meta.broken`(`object_type: fail`)
- `train.yaml` : `config_type: test_train_job`, `object_type: train`, `max_iters`, `model: file@./model.yaml`
- `model.yaml` : `patch`, `depth`
- `big.yaml` : 다른 `patch` - argv `file@` 로 `train.model` 을 바꿈
job 클래스와 설정은 `tests/support/_jobs.py` - job 프로세스가 다시 import 함.

바탕 자리는 케이스마다 빈 폴더(`tmp_path`) - `BASE_ROOT` 를 바꿔 끼움.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from support._jobs import JOBS, Train_Config

from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.job import FAILED, KILLED, STOPPED
from python_toolbox.run.launcher import LAUNCHER_LOGGER, Launcher, Launcher_Config
from python_toolbox.run.log import LOG_DIR, Detach

_RES = Path(__file__).parent / "resource" / "launcher"


@dataclass
class _Det_Config(Launcher_Config):
    note: str = ""


class _Det_Launcher(Launcher):
    config: _Det_Config
    JOB_REGISTRY = JOBS


class _Jobless_Launcher(Launcher):
    config: _Det_Config


def _Events(base_dir: Path) -> list[dict]:
    return [json.loads(_l) for _l in (base_dir / LOG_DIR / "events.jsonl").read_text().splitlines()]


def _Wait_until(ready, seconds: float = 30.0) -> None:
    """`ready()` 가 참이 될 때까지 기다림. 시간 안에 안 서면 실패."""
    _until = time.monotonic() + seconds
    while not ready():
        if time.monotonic() > _until:
            raise AssertionError("wait: condition not met in time")
        time.sleep(0.05)


def test_launcher_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path))
    _file = str(_RES / "launcher.yaml")

    # step : build - own config by the declared class, meta from its file, overrides on meta
    _launcher = _Det_Launcher(_file, ["train.model.patch=64"])
    assert type(_launcher.config) is _Det_Config and _launcher.config.log.level == "DEBUG", \
        "build: declared config class, nested config built"
    assert type(_launcher.config.log.output[0]).__name__ == "Log_Output", "build: list of configs built"
    assert _launcher.space.Get("train.max_iters") == 100, "build: meta file@ relative to the launcher file"
    assert _launcher.space.Get("train.model.patch") == 64, "build: override on meta"
    assert _launcher.base_dir == tmp_path / "det" and (_launcher.base_dir / LOG_DIR).is_dir(), \
        "build: base dir is the project name, log dir made at build"
    with pytest.raises(ValueError):
        _Det_Launcher(_file, ["train.max_iters"])
    with pytest.raises(FileNotFoundError):
        _Det_Launcher(str(_RES / "missing.yaml"))
    with pytest.raises(TypeError):
        _Jobless_Launcher(_file)

    # step : run - each job in its own process, results by name, job output in its own folder
    _results = _launcher.Run()
    _train = _launcher.space.Build("train", Train_Config)
    assert _results["train"] == (0, _train.Hash(), "Done"), "run: ok job -> (0, hash, Done)"
    assert _results["broken"][0] == FAILED, "run: failing job -> failed code"
    assert (_launcher.base_dir / "train" / "done.txt").read_text() == "64", "run: job wrote into its own folder"

    # step : records in one place - launcher: launched and ended per job, jobs: their own by default
    _all = _Events(_launcher.base_dir)
    assert {_e["name"] for _e in _all} == {LAUNCHER_LOGGER, "job.train", "job.broken"}, "record: launcher and jobs"
    _events = [_e for _e in _all if _e["name"] == LAUNCHER_LOGGER]
    assert sorted((_e["message"], _e["job"]) for _e in _events) == \
        [("job ended", "broken"), ("job ended", "train"), ("job launched", "broken"), ("job launched", "train")], \
        "record: launched and ended per job"
    assert sorted(_p.name for _p in _launcher.base_dir.iterdir()) == [LOG_DIR, "train"], "record: no config left"

    # step : a meta change after build reaches the next run; names pick the jobs to run
    _launcher.space.Override(["train.model.patch=7"])
    _named = _launcher.Run(["train"])
    assert set(_named) == {"train"} and _named["train"][0] == 0, "names: only the named job"
    assert (_launcher.base_dir / "train" / "done.txt").read_text() == "7", "change: built at run"
    with pytest.raises(KeyError):
        _launcher.Run(["nowhere"])

    # step : CLI - argv cut into the launcher file, overrides, job names; exit code is the number of not-ok jobs
    assert _Det_Launcher.Main([_file, "train", "train.model.patch=5"]) == 0, "cli: named job ok"
    assert (_launcher.base_dir / "train" / "done.txt").read_text() == "5", "cli: override reached the job"
    assert _Det_Launcher.Main([_file]) == 1, "cli: all jobs, one failed"
    with pytest.raises(ValueError):
        _Det_Launcher.Main([])
    with pytest.raises(KeyError):   # `=` 를 빠뜨린 덮어쓰기는 job 이름으로 읽혀 meta 에 없다고 실패
        _Det_Launcher.Main([_file, "train.max_iters10"])

    # step : a broken job config stops the run before any launch
    _count = len(_Events(_launcher.base_dir))
    for _bad, _error in [("train.max_iter=1", TypeError), ("broken.object_type=export", KeyError),
                         ("broken.config_type=", ValueError)]:
        _bad_launcher = _Det_Launcher(_file, [_bad])
        with pytest.raises(_error):
            _bad_launcher.Run()
    assert len(_Events(_launcher.base_dir)) == _count, "broken: nothing launched, nothing recorded"

    # step : a job process that ends without a result - its own exit code, or killed by a signal
    _code, _, _content = _Det_Launcher(_file, ["broken.object_type=crash"]).Run(["broken"])["broken"]
    assert _code == 5 and "without a result" in _content, "crash: exit code, no result"
    _code, _, _content = _Det_Launcher(_file, ["broken.object_type=killed"]).Run(["broken"])["broken"]
    assert _code == KILLED and "signal 9" in _content, f"killed: killed code {_code} {_content}"

    # step : stop from another thread while Run blocks - the waiting job ends by its own Work with the stop code
    _waiting = _Det_Launcher(_file, ["wait.config_type=test_train_job", "wait.object_type=wait"])
    _out: dict = {}
    _runner = threading.Thread(target=lambda: _out.update(_waiting.Run()))
    _runner.start()
    _Wait_until(lambda: any(_e["message"] == "job launched" and _e["job"] == "wait"
                            for _e in _Events(_waiting.base_dir)[_count:]))
    _waiting.Stop()
    _runner.join(timeout=30)
    assert not _runner.is_alive(), "stop: Run returned"
    assert _out["wait"][0] == STOPPED and set(_out) == {"train", "broken", "wait"}, \
        "stop: waiting job stopped, all results"
    _waiting.Stop()  # 도는 job 없음 - 할 일 없음

    # step : a consumer moves the base dir; argv file@ swaps a job part relative to cwd
    class _Elsewhere_Launcher(_Det_Launcher):
        def Make_base_dir(self) -> Path:
            _dir = tmp_path / "elsewhere" / self.config.project_name
            _dir.mkdir(parents=True, exist_ok=True)
            return _dir

    monkeypatch.chdir(_RES)
    _moved = _Elsewhere_Launcher(_file, ["train.model=file@./big.yaml"])
    assert _moved.Run()["train"][0] == 0, "override: job ran under the moved dir"
    assert (tmp_path / "elsewhere" / "det" / "train" / "done.txt").read_text() == "128", \
        "override: job got the moved dir and the swapped file"

    Detach(LAUNCHER_LOGGER)
