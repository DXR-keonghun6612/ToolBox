"""Job - 이름, 자기 설정, 바탕 자리로 지어지고, Work 를 돌려 `{이름: (코드, hash, 내용)}` 를 돌려줌. 결과 폴더를 만들고 이어 할 때 정체성을 비교.

입력 파일 없음. 바탕 자리는 케이스마다 빈 폴더(`tmp_path`), 기록은 pytest 의 `caplog` 와 job 이 쓴 파일.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import pytest

from python_toolbox.run.job import CONFIG_FILE, FAILED, OK, STOPPED, Job, Job_Config
from python_toolbox.run.log import LOG_DIR, Attach, Detach, Log_Config, Log_Output


@dataclass
class _Train_Config(Job_Config):
    epochs: int = 1


class _Quiet(Job):
    def Work(self) -> None:
        self.log.info("working")


class _Reports_error(Job):
    def Work(self) -> None:
        self.log.getChild("loader").error("broken sample")


class _Raises(Job):
    def Work(self) -> None:
        raise RuntimeError("boom")


class _Stops(Job):
    def Work(self) -> None:
        self.stop()


def test_job_flow(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    _config = _Train_Config()

    # step : clean work - result keyed by name, code 0, own config hash, summary record
    _out = _Quiet("quiet", _config, tmp_path).Run()
    assert _out == {"quiet": (OK, _config.Hash(), "Done")}, "ok: name -> (0, hash, Done)"
    _summary = caplog.records[-1]
    assert _summary.name == "job.quiet" and _summary.code == OK and _summary.errors == 0, "ok: summary fields"
    assert any(_r.getMessage() == "work started" and _r.started for _r in caplog.records), "ok: start time recorded"

    # step : an error record fails with the failed code - also from a child logger with its own declaration
    assert _Reports_error("err", _config, tmp_path).Run()["err"][0] == FAILED, "error record: failed code"
    Attach("job.err2.loader", Log_Config(output=[Log_Output(format="text", to="loader.log")]), tmp_path)
    assert _Reports_error("err2", _config, tmp_path).Run()["err2"][0] == FAILED, "error record: declared child counted"
    Detach("job.err2.loader")

    # step : an exception is logged, not raised, and fails
    assert _Raises("raise", _config, tmp_path).Run()["raise"][0] == FAILED, "exception: failed code"
    assert any(_r.exc_info and _r.levelno == logging.ERROR for _r in caplog.records), "exception: logged with trace"

    # step : a stop request ends with the stopped code
    _code, _, _content = _Stops("stop", _config, tmp_path).Run()["stop"]
    assert _code == STOPPED and _content == "Stopped", "stop: stopped code"

    # step : own declaration - records go to its own file under the log dir, detached after the run
    _logged = _Train_Config(log=Log_Config(output=[Log_Output(format="json", to="quiet.jsonl")]))
    _Quiet("own", _logged, tmp_path).Run()
    _lines = [json.loads(_l) for _l in (tmp_path / LOG_DIR / "quiet.jsonl").read_text().splitlines()]
    assert [_l["message"] for _l in _lines] == ["work started", "working", "work done"], "own log: every record"
    assert _logged.Hash() == _config.Hash(), "own log: declaration outside identity"

    # step : run dir - new one leaves the config, resume compares identity
    _job = _Quiet("quiet", _config, tmp_path)
    _run_dir = _job.Make_run_dir()
    assert _run_dir.parent == tmp_path and (_run_dir / CONFIG_FILE).is_file(), "run dir: under the base, config left"
    _same = _Train_Config(resume=str(_run_dir), log=Log_Config(level="DEBUG"))
    assert _Quiet("quiet", _same, tmp_path).Make_run_dir() == _run_dir, "resume: same identity passes"
    with pytest.raises(ValueError):
        _Quiet("quiet", _Train_Config(epochs=5, resume=str(_run_dir)), tmp_path).Make_run_dir()
    with pytest.raises(FileNotFoundError):
        _Quiet("quiet", _Train_Config(resume=str(tmp_path / "nowhere")), tmp_path).Make_run_dir()
