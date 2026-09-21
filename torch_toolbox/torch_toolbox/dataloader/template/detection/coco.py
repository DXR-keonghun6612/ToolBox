from __future__ import annotations
from dataclasses import dataclass

from .... import CFGS
from ... import DATASETS
from ...definition import Custom_Dataset, Dataset_Config


@CFGS.Register_module("COCO_Dataset_Config")
@dataclass
class COCO_Dataset_Config(Dataset_Config):
    config_type: str = "COCO_Dataset_Config"
    object_type: str = "COCO_Dataset"

    name: str = "coco"
    category: str = "detection"
    num_classes: int = 80
    bbox_format: str = "xywh"


@DATASETS.Register_module("COCO_Dataset")
class COCO_Dataset(Custom_Dataset):
    def Builder(self, data_dir: str, name: str, category: str, **kwargs):
        self.data_dir = data_dir
        self.num_classes = kwargs.get("num_classes", 80)
        self.samples: list = []

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        pass
