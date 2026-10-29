"""JSON file reader and writer."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import json

from ._base import File_Process, Handle_exp, Suffix_check, JSON_FILE_READ_ERROR


class Json(File_Process):
    """Handles JSON file persistence."""

    @classmethod
    @Handle_exp(extra_exp=JSON_FILE_READ_ERROR)
    def Read_from(
        cls, file: Path, enc: str = "UTF-8"
    ) -> tuple[bool, dict[str, Any]]:
        """Reads a JSON file into a dictionary.

        Args:
            file: Input JSON file path.
            enc: Text encoding.

        Returns:
            A tuple of ``(is_ok, data_dict)``.
        """
        _, _file = Suffix_check(file, ".json")

        if not _file.exists():
            return False, {}

        with _file.open(encoding=enc) as _f:
            return True, json.load(_f)

    @classmethod
    @Handle_exp()
    def Write_to(
        cls, file: Path, data: Any, enc: str = "UTF-8", indent: int = 4
    ) -> bool:
        """Writes data to a JSON file.

        Args:
            file: Output JSON file path.
            data: Data to serialize.
            enc: Text encoding.
            indent: JSON indentation level.

        Returns:
            ``True`` when the write succeeds.
        """
        cls.Ensure_dir(file)
        _, _path = Suffix_check(file, ".json", True)

        with _path.open(mode="w", encoding=enc) as _f:
            json.dump(data, _f, indent=indent, ensure_ascii=False)
        return True
