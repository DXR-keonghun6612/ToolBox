from __future__ import annotations
import random
from typing import Iterator, Sequence

from torch.utils.data import Sampler


class PK_Batch_Sampler(Sampler[list[int]]):
    """배치마다 class P 개 무작위 선택, class 당 표본 K 개. 표본이 K 미만인 class 는 중복 추출.

    Attributes:
        P: 배치당 class 수.
        K: class 당 표본 수.
        batch_size: P * K.
    """

    def __init__(
        self,
        class_ids: Sequence[int],
        P: int,
        K: int,
        num_batches: int | None = None,
        seed: int | None = None,
    ) -> None:
        if P <= 0 or K <= 0:
            raise ValueError(f"P, K는 양수여야 함 (P={P}, K={K})")

        self.P = P
        self.K = K
        self.batch_size = P * K

        self._cls_to_idx: dict[int, list[int]] = {}
        for _idx, _cid in enumerate(class_ids):
            self._cls_to_idx.setdefault(int(_cid), []).append(_idx)

        self._classes = list(self._cls_to_idx.keys())
        if P > len(self._classes):
            raise ValueError(f"P={P}가 unique class 수({len(self._classes)})를 초과함")

        self._num_batches = (
            num_batches if num_batches is not None
            else max(1, len(class_ids) // self.batch_size)
        )
        self._rng = random.Random(seed) if seed is not None else random.Random()

    def __iter__(self) -> Iterator[list[int]]:
        for _ in range(self._num_batches):
            _selected = self._rng.sample(self._classes, self.P)
            _batch: list[int] = []
            for _cid in _selected:
                _pool = self._cls_to_idx[_cid]
                _batch.extend(
                    self._rng.sample(_pool, self.K) if len(_pool) >= self.K
                    else self._rng.choices(_pool, k=self.K)
                )
            yield _batch

    def __len__(self) -> int:
        return self._num_batches
