"""기록 - logger 마다 선언(수준, 출력 목록)을 걸고, 선언한 logger 의 record 는 그 선언 출력에만, 같은 출력은 하나를 같이 쓰고, 다시 걸어도 겹치지 않음.

입력 파일 없음. 기록 파일은 케이스마다 빈 폴더(`tmp_path`).
"""
from __future__ import annotations

import json
import logging

import pytest

from python_toolbox.run.log import Attach, Begin_run, Detach, Log_Config, Log_Output


def _Lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _Out(format: str, to: str) -> Log_Output:
    return Log_Output(format=format, to=to)


def test_log_flow(tmp_path, capsys):
    _root = Log_Config(level="INFO", output=[_Out("text", "stderr"), _Out("text", "run.log"),
                                             _Out("json", "events.jsonl")])
    _train = Log_Config(level="DEBUG", output=[_Out("text", "run.log"), _Out("json", "events.jsonl")])
    _metric = Log_Config(level="INFO", output=[_Out("json", "metrics.jsonl"), _Out("json", "stdout")])

    # step : attach and write - each logger its own threshold, declared records only to their own outputs
    Attach("", _root, tmp_path)
    Attach("train", _train, tmp_path)
    Attach("metric", _metric, tmp_path)
    logging.getLogger("other").debug("hidden by root threshold")
    logging.getLogger("other").warning("shown by root")
    logging.getLogger("train.loader").debug("batch %d", 3)
    logging.getLogger("metric").info("step", extra={"step": 100, "loss": 0.31})

    _text = _Lines(tmp_path / "run.log")
    assert len(_text) == 2, "text: root warning and train debug, shared file written once per record"
    assert " WARNING other - shown by root" in _text[0], "text: level kept per line"
    assert " DEBUG train.loader - batch 3" in _text[1], "text: child logger follows its nearest declaration"

    _events = [json.loads(_l) for _l in _Lines(tmp_path / "events.jsonl")]
    assert [_e["level"] for _e in _events] == ["WARNING", "DEBUG"], "jsonl: same records, structured"

    _metrics = [json.loads(_l) for _l in _Lines(tmp_path / "metrics.jsonl")]
    assert len(_metrics) == 1 and _metrics[0]["step"] == 100 and _metrics[0]["loss"] == 0.31, \
        "jsonl: extra fields as keys, metric declaration only"
    _out = capsys.readouterr()
    assert json.loads(_out.out.strip())["step"] == 100, "stdout: json lines stream"
    assert "shown by root" in _out.err and "batch" not in _out.err, "stderr: root text, train not shown there"

    # step : bad declarations fail before anything changes
    with pytest.raises(ValueError):
        Attach("x", Log_Config(level="LOUD"), tmp_path)
    with pytest.raises(ValueError):
        Attach("x", Log_Config(output=[_Out("yaml", "stderr")]), tmp_path)
    with pytest.raises(ValueError):
        Attach("x", Log_Config(output=[_Out("text", "x.log")]), None)
    with pytest.raises(ValueError):
        Attach("x", Log_Config(output=[_Out("json", "run.log")]), tmp_path)
    logging.getLogger("train").info("still declared")
    assert _Lines(tmp_path / "run.log")[-1].endswith("INFO train - still declared"), "bad: old declarations kept"

    # step : time slot in a file name is the run start
    _stamp = Begin_run()
    Attach("timed", Log_Config(output=[_Out("text", "job_{time}.log")]), tmp_path)
    logging.getLogger("timed").info("stamped")
    assert (tmp_path / f"job_{_stamp}.log").is_file(), "time: file named by the run start"

    # step : detach and attach again - no doubled lines, detached logger goes back to its parent's declaration
    Detach("train")
    Attach("", Log_Config(level="INFO", output=[_Out("text", "run.log")]), tmp_path)
    logging.getLogger("train").info("after reset")
    _text = _Lines(tmp_path / "run.log")
    assert _text[-1].endswith("INFO train - after reset") and _text.count(_text[-1]) == 1, "reset: one line, to root"

    for _name in ("", "metric", "timed"):
        Detach(_name)
