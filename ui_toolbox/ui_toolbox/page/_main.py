"""main 골격 - root page. config 를 central widget 에 채움, 닫힐 때 멈출 것을 모아 둠.

- `QMainWindow` 는 제 layout 이 있음 - `Fill` 은 central widget 에
- root 묶음(`items`, `link`, `action`)을 그대로 올림. `find` 는 `items.find` - `QWidget.find`(정적, WId)를 여기서만 가림
- 공통 style(`Base`)이 root 의 `style` 아래에 깔림
- 상태, 입력의 뜻, 연결은 상속한 소비처 page
- 작업은 python_toolbox launcher 하나(`launcher`) - `launch` 가 작업 스레드에서 `Run`, 진행은 popup 이 기록 파일로 보임
- 멈춤 버튼, 창 닫기는 `launcher.Stop` - 끝내는 것은 job
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMainWindow, QWidget
from python_toolbox.file import Make_dict_from
from python_toolbox.run.launcher import Launcher
from python_toolbox.run.log import EVENT_FILE, LOG_DIR

from ._progress import Progress_popup
from ._style import Base, Tokens
from .builder import Fill

__all__ = ["Main"]


class Main(QMainWindow):
    """root page 하나.

    Attributes:
        items: root 의 배치에 드는 node
        link: root 의 popup
        action: root 의 `QAction`
        launcher: 돌릴 작업. 소비처가 넣음 - 비면 `launch` 못 함
    """

    def __init__(self, config: dict | str | Path, base: str | Path = ".", tokens: dict[str, Any] | None = None,
                 parent: QWidget | None = None) -> None:
        """Args:
        config: root node, 또는 그것을 담은 yaml 경로 - 경로면 `base` 는 그 폴더.
        base: `items` 파일 경로의 기준 폴더.
        tokens: 덮을 토큰 - `Tokens` 의 이름.
        parent: 부모 위젯.

        Raises:
            ValueError: config 파일을 맵으로 못 읽을 때. 나머지는 `Fill`, `Tokens` 와 같음.
        """
        super().__init__(parent)
        if not isinstance(config, dict):
            _path = Path(config)
            _ok, _data = Make_dict_from(_path)
            if not _ok or not isinstance(_data, dict):
                raise ValueError(f"cannot read a map from {_path}")
            config, base = _data, _path.parent
        self._stops: list[Callable[[], Any]] = []
        _body = QWidget()
        Fill(_body, config, base, Base(Tokens(**(tokens or {}))))
        self.setCentralWidget(_body)
        self.setWindowTitle(config.get("title", ""))
        self.items = _body.items
        self.link = _body.link
        self.action = _body.action
        self.launcher: Launcher | None = None
        self._launch_popups: set[int] = set()
        self.on_close(self._stop_launcher)

    def find(self, path: str) -> Any:
        """`items.find` - `.` 으로 이은 key 경로의 객체.

        Raises:
            KeyError: 없는 key 일 때, 중간 segment 가 container 가 아닐 때.
        """
        return self.items.find(path)

    def on_close(self, stop: Callable[[], Any]) -> None:
        """창이 닫힐 때 부를 것 - 감시, 타이머, 프로세스 멈춤. 넣은 차례로 부름."""
        self._stops.append(stop)

    def launch(self, popup: Progress_popup, lock: tuple[QWidget, ...] = (), names: Sequence[str] | None = None) -> None:
        """`launcher.Run(names)` 을 작업 스레드에서 돌리고 popup 에 보임. 결과는 `end` - 모든 job 이 0 이면 성공.

        popup 은 바탕 자리의 기록 파일을 따라 읽음, 전체는 돌릴 job 수. 멈춤 버튼은 `launcher.Stop`.

        Args:
            popup: 진행 화면.
            lock: 끝까지 잠글 위젯.
            names: 돌릴 job 이름. 비면 meta 의 job 전부.

        Raises:
            RuntimeError: `launcher` 가 빔. popup 의 앞 진행이 안 끝남 - `Progress_popup.begin` 그대로.
            KeyError, ValueError: meta 의 참조가 깨짐 - `Config_Space.Get` 그대로.
        """
        if self.launcher is None:
            raise RuntimeError(f"{type(self).__name__}.launcher is not set")
        _launcher = self.launcher
        _names = list(_launcher.space.Get()) if names is None else list(names)
        if id(popup) not in self._launch_popups:
            popup.stop_requested.connect(self._stop_launcher)
            self._launch_popups.add(id(popup))
        popup.begin(lock, log_file=_launcher.base_dir / LOG_DIR / EVENT_FILE, total=len(_names))
        threading.Thread(target=_Run_launcher, args=(_launcher, popup, _names), name="launcher-run", daemon=True).start()

    def _stop_launcher(self) -> None:
        if self.launcher is not None:
            self.launcher.Stop()

    def closeEvent(self, event) -> None:
        for _stop in self._stops:
            _stop()
        super().closeEvent(event)


def _Run_launcher(launcher: Launcher, popup: Progress_popup, names: list[str]) -> None:
    """작업 스레드 하나 - `Run` 의 결과로 popup 을 끝냄. 띄우기 전 실패(설정 짓기, 없는 이름 등)는 그 사유를 로그 칸에."""
    try:
        _results = launcher.Run(names)
    except Exception as _e:  # noqa: BLE001 - 작업 스레드의 실패는 popup 의 끝으로 보임, 다시 던지면 아무도 못 받음
        popup.line(f"{type(_e).__name__}: {_e}")
        popup.end(False, "not launched")
        return
    _ok = sum(1 for _code, _, _ in _results.values() if _code == 0)
    popup.end(_ok == len(_results), f"{_ok} / {len(_results)} ok")
