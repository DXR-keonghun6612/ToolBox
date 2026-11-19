"""Workspace template utilities for repeatable project runs."""
from __future__ import annotations
import time
import uuid
from pathlib import Path


RESULT_ROOT = "./result"


class Project_Template:
    """Allocates a unique workspace and provides idempotent setup.

    The template is intentionally independent from any config type. Subclasses
    are expected to define their own execution entrypoints on top of the
    workspace lifecycle.
    """

    def __init__(self, project_name: str):
        """Initializes the workspace template.

        Args:
            project_name: Stable project identifier used in the workspace path.

        Raises:
            ValueError: If ``project_name`` is empty.
        """
        if not project_name:
            raise ValueError("[ERROR] Project name cannot be empty.")

        self.project_name = project_name
        _run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.workspace = Path(RESULT_ROOT) / project_name / _run_id

        self._is_setup_done = False

    def _Setup(self) -> bool:
        """Creates the workspace directory once.

        Returns:
            ``False`` on the first call after creating the directory, and
            ``True`` on repeated calls.
        """
        if self._is_setup_done:
            return True

        self.workspace.mkdir(parents=True, exist_ok=True)
        self._is_setup_done = True
        return False
