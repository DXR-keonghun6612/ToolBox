"""root page 의 launcher - `launch` 가 `Run` 을 작업 스레드에서 돌리고, popup 이 기록 파일의 새 줄을 로그 칸으로,
`job ended` 수를 진행으로 보임. 멈춤 버튼은 `launcher.Stop`.

입력 `test/resource/launch/launcher.yaml` : `project_name: ui`, `meta.quick`(`object_type: quick`), `meta.broken`(`object_type: fail`).
job 과 launcher 는 `test/support/_launch_jobs.py` - job 프로세스가 다시 import 함. 바탕 자리는 빈 폴더(`tmp_path`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from python_toolbox.run import launcher as launcher_module
from python_toolbox.run.launcher import LAUNCHER_LOGGER
from python_toolbox.run.log import Detach
from support._launch_jobs import Ui_Launcher

from ui_toolbox.page import Main, Progress_popup

_FILE = str(Path(__file__).parents[1] / "resource" / "launch" / "launcher.yaml")


def _wait(ready, ms: int = 30000) -> None:
    """`ready()` 가 참이 될 때까지 이벤트를 돌림. 시간 안에 안 서면 실패."""
    for _ in range(ms // 20):
        if ready():
            return
        QTest.qWait(20)
    raise AssertionError("wait: condition not met in time")


def test_main_launch_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module, "BASE_ROOT", str(tmp_path))
    _main = Main({"class": "qt_QVBoxLayout"})
    _pop = Progress_popup()

    # step : no launcher - nothing to run
    with pytest.raises(RuntimeError):
        _main.launch(_pop)

    # step : run - every line of the launcher and the jobs in the log, ended jobs as progress, summary at the end
    _main.launcher = Ui_Launcher(_FILE)
    _main.launch(_pop)
    with pytest.raises(RuntimeError):
        _main.launch(_pop)
    _wait(lambda: not _pop.running)
    _lines = _pop.log.toPlainText().splitlines()
    assert any("launcher - job ended" in _l for _l in _lines), "run: launcher lines"
    assert any("job.quick - quick work" in _l for _l in _lines), "run: job lines"
    assert any("job.broken - broken" in _l for _l in _lines), "run: every job's lines"
    assert (_pop.bar.value(), _pop.bar.maximum()) == (2, 2), "run: ended jobs over meta jobs"
    assert _pop.state.text().startswith("끝 - 실패") and "1 / 2 ok" in _pop.state.text(), f"run: {_pop.state.text()}"

    # step : run by name - only the named job, progress over the named jobs
    _main.launch(_pop, names=["quick"])
    _wait(lambda: not _pop.running)
    assert (_pop.bar.value(), _pop.bar.maximum()) == (1, 1), "names: progress over the named jobs"
    assert "job.broken" not in _pop.log.toPlainText() and "1 / 1 ok" in _pop.state.text(), "names: only the named job"

    # step : stop - the button asks the launcher, the waiting job ends by its own work with the stop code
    _main.launcher = Ui_Launcher(_FILE, ["broken.object_type=wait"])
    _main.launch(_pop)
    _wait(lambda: "job.broken - work started" in _pop.log.toPlainText())
    _pop._stop.click()
    _wait(lambda: not _pop.running)
    _lines = _pop.log.toPlainText().splitlines()
    assert any("job stop requested" in _l for _l in _lines), "stop: request recorded"
    assert any("job.broken - work failed" in _l for _l in _lines), "stop: waiting job ended early"
    assert "1 / 2 ok" in _pop.state.text(), f"stop: stopped job is not ok {_pop.state.text()}"

    # step : a run that fails before launch - the reason in the log, ended as failed
    _main.launcher = Ui_Launcher(_FILE, ["quick.object_type=nowhere"])
    _main.launch(_pop)
    _wait(lambda: not _pop.running)
    assert "KeyError" in _pop.log.toPlainText() and _pop.state.text().startswith("끝 - 실패"), "not launched: failed"
    assert _pop.log.toPlainText().count("job launched") == 0, "not launched: nothing launched"
    _pop.close()
    _main.close()

    Detach(LAUNCHER_LOGGER)
