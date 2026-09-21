from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import torch
import torch.nn as nn
from torch import Tensor
from torch.export import Dim
from torchvision import transforms
from torchvision.io import read_image, ImageReadMode

from .... import CFGS
from ... import DATASETS
from ...functional.image_net import Get_transform
from ._base import Classification_Dataset, Classification_Dataset_Config


OBJECT_TYPE = "classification_image_dataset"
CONFIG_NAME = f"{OBJECT_TYPE}_Config"


@CFGS.Register_module(CONFIG_NAME)
@dataclass
class Classification_Image_Dataset_Config(Classification_Dataset_Config):
    config_type: str = CONFIG_NAME
    object_type: str = OBJECT_TYPE

    name: str = "classification"
    category: str = "classification"
    transform: str | None = "ImageNet"


@DATASETS.Register_module(OBJECT_TYPE)
class Classification_Image_Dataset(Classification_Dataset):
    """폴더 구조 image classification dataset. 항목 = `{"image", "class_id", "category_id"}`.

    data_dir/name/
    |-- id_map.yaml   (형식은 `_Load_id_map`)
    |-- class_a/image1.jpg, ...
    `-- class_b/...
    """

    layout: str = "NCHW"
    data_format: str = "RGB"

    samples: list[tuple[Path, int, int]]
    transform: transforms.Compose | None

    def Builder(
        self,
        data_dir: str,
        name: str,
        category: str,
        id_map_file: str = "id_map.yaml",
        transform: str | None = "ImageNet",
        extensions: list[str] | None = None,
        **kwargs,
    ):
        super().Builder(
            data_dir, name, category,
            id_map_file=id_map_file,
            extensions=extensions,
            **kwargs,
        )
        self.transform = Get_transform(transform)

    def _Scan_samples(
        self, root: Path, extensions: list[str] | None = None, **kwargs
    ) -> list[tuple[Path, int, int]]:
        _exts = set(extensions or [".jpg", ".jpeg", ".png", ".bmp"])
        _samples = []
        for _class_dir in sorted(root.iterdir()):
            if not _class_dir.is_dir() or _class_dir.name not in self.id_map:
                continue
            _cid, _catid = self.id_map[_class_dir.name]
            for _p in sorted(_class_dir.iterdir()):
                if _p.suffix.lower() in _exts:
                    _samples.append((_p, _cid, _catid))
        return _samples

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        _path, _class_id, _category_id = self.samples[index]
        _img = read_image(str(_path), mode=ImageReadMode.RGB)
        if self.transform:
            _img = self.transform(_img)
        return {
            "image": _img,
            "class_id": torch.tensor(_class_id, dtype=torch.long),
            "category_id": torch.tensor(_category_id, dtype=torch.long),
        }
