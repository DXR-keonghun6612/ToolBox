"""기록 - logger 마다 수준과 출력 위치를 걸고, 줄마다 수준이 남고, 형식이 확장자로 갈리고, 다시 걸어도 겹치지 않음.

입력 파일 없음. 기록 파일은 케이스마다 빈 폴더(`tmp_path`).
"""
from __future__ import annotations

import json
import logging

import pytest

from python_toolbox.run.log import CONSOLE, Log_Config, Setup_log


def _Lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_log_flow(tmp_path):
    _log = {
        "root": Log_Config(level="INFO", to=[CONSOLE, "run.log", "events.jsonl"]),
        "train": Log_Config(level="DEBUG", to=["run.log", "events.jsonl"]),
        "metric": Log_Config(level="INFO", to=["metrics.jsonl"]),
    }

    # step : set up and write - each line keeps its own level, each logger its own threshold and places
    Setup_log(tmp_path, _log)
    logging.getLogger("other").debug("hidden by root threshold")
    logging.getLogger("other").warning("shown by root")
    logging.getLogger("train.loader").debug("batch %d", 3)
    logging.getLogger("metric").info("step", extra={"step": 100, "loss": 0.31})

    _text = _Lines(tmp_path / "run.log")
    assert len(_text) == 2, "text: root warning and train debug only"
    assert " WARNING other - shown by root" in _text[0], "text: level kept per line"
    assert " DEBUG train.loader - batch 3" in _text[1], "text: child logger follows its configured parent"

    _events = [json.loads(_l) for _l in _Lines(tmp_path / "events.jsonl")]
    assert [_e["level"] for _e in _events] == ["WARNING", "DEBUG"], "jsonl: same records, structured"

    _metrics = [json.loads(_l) for _l in _Lines(tmp_path / "metrics.jsonl")]
    assert _metrics == [_metrics[0]] and _metrics[0]["step"] == 100 and _metrics[0]["loss"] == 0.31, \
        "jsonl: extra fields as keys, metric logger only"

    # step : bad config fails before anything is attached
    with pytest.raises(ValueError):
        Setup_log(tmp_path, {"root": Log_Config(level="LOUD")})
    with pytest.raises(ValueError):
        Setup_log(tmp_path, {"root": Log_Config(to=["run.txt"])})
    with pytest.raises(ValueError):
        Setup_log(None, {"root": Log_Config(to=["run.log"])})
    with pytest.raises(FileNotFoundError):
        Setup_log(tmp_path / "nowhere", {"root": Log_Config(to=["run.log"])})

    # step : set up again - no doubled lines, old per-logger setup undone
    Setup_log(tmp_path, {"root": Log_Config(level="INFO", to=["run.log"])})
    logging.getLogger("train").info("after reset")
    _text = _Lines(tmp_path / "run.log")
    assert _text[-1].endswith("INFO train - after reset") and len(_text) == 3, "reset: one line, train back to root"

    Setup_log(None, {"root": Log_Config(level="WARNING", to=[CONSOLE])})
