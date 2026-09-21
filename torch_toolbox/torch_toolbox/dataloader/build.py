from __future__ import annotations
from typing import cast

from torch.utils.data import DataLoader, DistributedSampler

from .. import CFGS, Mode
from . import DATASETS, DATALOADER_FN
from .definition import Custom_Dataset, Dataset_Config, Dataloader_Config
from .functional import PK_Batch_Sampler
from .template import Classification_Dataset, Classification_Dataset_Config


def _Get_collate_func(name: str | None):
    if name is None:
        return None
    return DATALOADER_FN.Get(name)


def Build_dataset(
    config: Dataset_Config | Classification_Dataset_Config,
    mode: Mode,
) -> Custom_Dataset | Classification_Dataset:
    """
    Raises:
        ValueError: `object_type` 이 `DATASETS` 에 미등록.
    """
    _cls = DATASETS.Get(config.object_type)
    if _cls is None:
        raise ValueError(f"'{config.object_type}'가 DATASETS에 미등록.")
    return _cls(mode=mode, **config.Extract())


def Build_dataloader(
    dataloader_cfg: Dataloader_Config,
    mode: Mode,
    world_size: int = 1,
    rank: int = 0,
) -> tuple[Custom_Dataset | Classification_Dataset, DataLoader]:
    """`dataset_meta` 에서 dataset 생성 + DataLoader.

    - `pk_sampler` + TRAIN + 단일 GPU + `Classification_Dataset` : `PK_Batch_Sampler`
    - `world_size >= 2` : `DistributedSampler`. 셔플은 sampler 가
    - 그 외 : 기본 DataLoader

    Args:
        dataloader_cfg: DataLoader 설정.
        mode: 실행 mode.
        world_size: 전체 프로세스 수.
        rank: 글로벌 rank.

    Returns:
        (dataset, DataLoader).
    """
    _meta = dataloader_cfg.dataset_meta
    _ds_cfg = cast(Dataset_Config, CFGS.Get(_meta["config_type"])(**_meta))
    _dataset = Build_dataset(_ds_cfg, mode)

    _collate_fn = _Get_collate_func(dataloader_cfg.collate_fn)

    if (
        dataloader_cfg.pk_sampler is not None
        and mode == Mode.TRAIN
        and world_size < 2
        and isinstance(_dataset, Classification_Dataset)
    ):
        _pk = dataloader_cfg.pk_sampler
        _batch_sampler = PK_Batch_Sampler(
            class_ids=_dataset.class_ids,
            P=int(_pk["P"]),
            K=int(_pk["K"]),
            num_batches=_pk.get("num_batches"),
            seed=_pk.get("seed"),
        )
        return _dataset, DataLoader(
            _dataset,
            batch_sampler=_batch_sampler,
            num_workers=dataloader_cfg.num_workers,
            pin_memory=dataloader_cfg.pin_memory,
            collate_fn=_collate_fn,
        )

    if world_size >= 2:
        _sampler = DistributedSampler(
            _dataset,
            num_replicas=world_size,
            rank=rank,
            shuffle=dataloader_cfg.shuffle if mode == Mode.TRAIN else False,
        )
        _shuffle = False
    else:
        _sampler = None
        _shuffle = dataloader_cfg.shuffle

    return _dataset, DataLoader(
        _dataset,
        batch_size=dataloader_cfg.batch_size,
        num_workers=dataloader_cfg.num_workers,
        shuffle=_shuffle,
        drop_last=dataloader_cfg.drop_last,
        pin_memory=dataloader_cfg.pin_memory,
        collate_fn=_collate_fn,
        sampler=_sampler,
    )
