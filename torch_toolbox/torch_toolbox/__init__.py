from enum import StrEnum

from python_toolbox.registry import Registry
from python_toolbox.schema import Base_Config


class Mode(StrEnum):
    TRAIN = "train"
    VALIDATION = "val"
    TEST = "test"


CFGS = Registry[type[Base_Config]]("torch_config", Base_Config)
