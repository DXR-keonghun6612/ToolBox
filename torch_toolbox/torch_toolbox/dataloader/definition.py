from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, ClassVar

from torch import Tensor
import torch.nn as nn
from torch.utils.data import Dataset

from python_toolbox.project import Base_Config

from .. import Mode


@dataclass
class Dataset_Config(Base_Config):
    """데이터셋 Config.

    Attributes:
        config_type: `CFGS` 조회 키.
        object_type: `DATASETS` 조회 키.
        data_dir: 데이터셋 루트.
        name: 데이터셋 이름.
        category: 카테고리 서브셋.
        data_kwargs: 서브클래스별 추가 설정. `Extract()` 에서 언패킹, `Builder()` 키워드 인자.
    """

    __unpack_extract__: ClassVar[set[str]] = {"data_kwargs"}

    config_type: str = "Dataset_Config"
    object_type: str = "Base_Dataset"

    data_dir: str = "./datasets"
    name: str = "no_data"
    category: str = "not_use"
    data_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Dataloader_Config(Base_Config):
    """DataLoader Config.

    Attributes:
        batch_size: 배치 크기.
        num_workers: 워커 수.
        shuffle: 에폭마다 셔플. DDP 에서는 `DistributedSampler` 가 대신함.
        drop_last: 마지막 불완전 배치 제거.
        pin_memory: 핀 메모리.
        collate_fn: `DATALOADER_FN` 키. None 이면 기본 collate.
        pk_sampler: `PK_Batch_Sampler` 인자 (`P`, `K`, `num_batches`, `seed`). 단일 GPU TRAIN 에서만 적용.
        dataset_meta: `Dataset_Config` raw dict. `Build_dataloader` 가 `CFGS` 로 인스턴스화.
    """

    __exclude_extract__: ClassVar[set[str]] = {"pk_sampler", "dataset_meta"}

    batch_size: int = 1
    num_workers: int = 0
    shuffle: bool = True
    drop_last: bool = False
    pin_memory: bool = False
    collate_fn: str | None = None
    pk_sampler: dict[str, Any] | None = None
    dataset_meta: dict[str, Any] = field(default_factory=dict)


class Custom_Dataset(Dataset):
    """데이터셋 추상 기반. 서브클래스는 `Builder`, `__len__`, `__getitem__`, (export 시) `Info_for_onnx` 구현.

    Attributes:
        layout: 데이터 레이아웃 (예 "NCHW"). ONNX export 메타데이터.
        data_format: 데이터 포맷 (예 "RGB_uint8"). ONNX export 메타데이터.
        mode: 실행 mode.
    """

    layout: str = ""
    data_format: str = ""

    def __init__(self, mode: Mode, **kwargs):
        self.mode = mode
        self.Builder(**kwargs)

    def Builder(self, data_dir: str, name: str, category: str, **kwargs):
        """
        Args:
            data_dir: 데이터셋 루트.
            name: 데이터셋 이름.
            category: 카테고리 서브셋.
            **kwargs: `Dataset_Config.data_kwargs`.
        """
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError

    def __getitem__(self, index) -> Any:
        raise NotImplementedError

    def Info_for_onnx(self) -> tuple[
        nn.Module | None,
        tuple[Tensor, ...],
        dict[str, Any],
        dict[str, Any],
    ]:
        """ONNX export 정보.

        Returns:
            (preprocess_layer, dummy_inputs, onnx_kwargs, runtime_kwargs).

            - preprocess_layer: 모델 앞에 붙일 전처리. 없으면 None
            - dummy_inputs: `torch.onnx.export` 더미 입력. 입력 순서대로
            - onnx_kwargs: `torch.onnx.export` 추가 인자 (`input_names`, `output_names`, `dynamic_shapes` 등)
            - runtime_kwargs: TensorRT 런타임 설정. `input_profiles`, `output_profiles` 필수.
              항목은 텐서 하나 = `{"name", "dtype", "min_shape", "opt_shape", "max_shape"}`,
              `name` 은 `input_names` / `output_names` 와 일치
        """
        raise NotImplementedError
