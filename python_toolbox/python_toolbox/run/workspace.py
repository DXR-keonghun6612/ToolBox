"""실행 결과 자리 - 실행마다 폴더 하나(`result/<이름>/<시각_id>`)를 잡고 한 번만 만듦."""
from __future__ import annotations
import time
import uuid
from pathlib import Path


#: 결과 자리의 맨 위 - 실행한 폴더(cwd) 기준.
RESULT_ROOT = "./result"


class Workspace:
    """실행 하나의 결과 자리. 설정 꼴을 모름 - 실행 진입점은 서브클래스가 이 위에 지음.

    Attributes:
        project_name: 결과 자리 경로에 쓰는 이름.
        workspace: 이번 실행의 폴더 - `_Setup` 이 만듦.
    """

    def __init__(self, project_name: str):
        """Args:
            project_name: 결과 자리 경로에 쓰는 이름. 실행마다 같음.

        Raises:
            ValueError: `project_name` 이 비었을 때.
        """
        if not project_name:
            raise ValueError("project_name is empty")

        self.project_name = project_name
        _run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.workspace = Path(RESULT_ROOT) / project_name / _run_id

        self._is_setup_done = False

    def _Setup(self) -> bool:
        """폴더를 한 번만 만듦.

        Returns:
            처음 불러 만들었으면 거짓, 이미 만든 뒤면 참.
        """
        if self._is_setup_done:
            return True

        self.workspace.mkdir(parents=True, exist_ok=True)
        self._is_setup_done = True
        return False
