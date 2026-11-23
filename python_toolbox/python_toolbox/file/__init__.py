"""파일 읽기, 쓰기 - 확장자로 처리기를 고름(`FILE_PROCESS`). text, JSON, YAML, CSV.

새 포맷은 `File_Process` 파생 처리기를 `FILE_PROCESS` 에 등록 하나.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, cast

from ._base import File_Process
from ._text import Text
from ._json import Json
from ._yaml import Yaml
from ._csv import Csv
from .group import Make_the_file_group


FILE_PROCESS: dict[str, type[File_Process]] = {
    ".txt": Text,
    ".json": Json,
    ".yaml": Yaml,
    ".csv": Csv,
}


def _resolve(file: Path) -> type[File_Process]:
    if not Path.is_file(file):
        raise ValueError(f"!!! This path {file} is not FILE !!!")
    _processor = FILE_PROCESS.get(file.suffix.lower())
    if _processor is None:
        raise ValueError(f"File extension '{file.suffix}' is not supported")
    return _processor


def Read_from(file: Path, enc: str = "UTF-8", **kwarg) -> tuple[bool, Any]:
    return _resolve(file).Read_from(file, enc, **kwarg)


def Make_dict_from(
    file: Path, enc: str = "UTF-8", **kwarg
)-> tuple[bool, dict]:
    _done, _data = Read_from(file, enc, **kwarg)
    return _done, cast(dict, _data)


def Make_list_from(
    file: Path, enc: str = "UTF-8", **kwarg
) -> tuple[bool, list]:
    _done, _data = Read_from(file, enc, **kwarg)
    return _done, cast(list, _data)


def Write_to(file: Path, data: Any, enc: str = "UTF-8", **kwarg) -> None:
    _processor = FILE_PROCESS.get(file.suffix.lower())
    if _processor is None:
        raise ValueError(
            f"File extension '{file.suffix}' is not supported for writing.")
    _processor.Write_to(file, data, enc, **kwarg)


__all__ = [
    "FILE_PROCESS",
    "Read_from",
    "Make_dict_from",
    "Make_list_from",
    "Write_to",
    "Make_the_file_group",
]
