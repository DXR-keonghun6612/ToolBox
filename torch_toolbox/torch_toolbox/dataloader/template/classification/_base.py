from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import yaml

from ...definition import Custom_Dataset, Dataset_Config


@dataclass
class Classification_Dataset_Config(Dataset_Config):
    """폴더 구조 classification dataset 공통 Config.

    Attributes:
        id_map_file: id_map YAML 파일명 (`data_dir/name/` 기준).
        transform: `Get_transform` 키. None 이면 원본.
        extensions: 수집할 파일 확장자.
    """

    id_map_file: str = "id_map.yaml"
    transform: str | None = None
    extensions: list[str] = field(default_factory=lambda: [".jpg", ".jpeg", ".png", ".bmp"])


class Classification_Dataset(Custom_Dataset):
    """폴더 구조 classification dataset 공통 기반. 서브클래스는 `_Scan_samples` 구현.

    Attributes:
        samples: `(item, class_id, category_id)` 리스트.
        id_map: class_name -> `(class_id, category_id)`.
        class_map: class_id -> `(class_name, category_id)`.
        class_ids: 샘플별 class_id. `PK_Batch_Sampler` 입력.
    """

    samples: list[tuple[Any, int, int]]
    id_map: dict[str, tuple[int, int]]

    def Builder(
        self,
        data_dir: str,
        name: str,
        category: str,
        id_map_file: str = "id_map.yaml",
        **kwargs,
    ):
        """id_map 로드 -> 샘플 스캔. id_map 파일이 없으면 폴더명으로 생성 후 재스캔.

        Args:
            data_dir: 데이터셋 루트.
            name: 데이터셋 이름. 실제 루트는 `data_dir/name/`.
            category: 카테고리 서브셋.
            id_map_file: id_map YAML 파일명.
            **kwargs: `_Scan_samples` 추가 인자.
        """
        _root = Path(data_dir) / name
        self.id_map = self._Load_id_map(_root / id_map_file)
        self.samples = self._Scan_samples(_root, **kwargs)

        if not self.id_map:
            self.id_map = self._Auto_id_map(_root)
            self.samples = self._Scan_samples(_root, **kwargs)

    def _Scan_samples(
        self, root: Path, **kwargs
    ) -> list[tuple[Any, int, int]]:
        """루트 스캔 -> `(item, class_id, category_id)` 리스트. `id_map` 설정 뒤 호출됨.

        Args:
            root: 데이터셋 루트.
            **kwargs: 서브클래스별 추가 인자.
        """
        raise NotImplementedError

    @property
    def class_ids(self) -> list[int]:
        return [_s[1] for _s in self.samples]

    def __len__(self) -> int:
        return len(self.samples)

    def _Load_id_map(self, map_path: Path) -> dict[str, tuple[int, int]]:
        """id_map YAML 로드. `class_map`, `id_map_path` 도 채움.

        형식 : 바깥 키는 호출번호 (나열 순서), `class_id` 는 별도 필드::

            0: {class_id: 0, name: no_label,     category_id: 6}
            1: {class_id: 1, name: 10D132000NT9, category_id: 2}

        마지막 호출번호 + 1 != 항목 수면 경고.

        Args:
            map_path: id_map YAML 경로.

        Returns:
            class_name -> `(class_id, category_id)`. 파일이 없으면 빈 dict.

        Raises:
            ValueError: 옛 형식 (`{name: {class_id, category_id}}`).
        """
        self.class_map = {}
        self.id_map_path = map_path
        if not map_path.exists():
            print(
                f"[WARN] id_map 파일이 없다: {map_path.resolve()}\n"
                f"       (data_dir/name 기준 상대경로 '{map_path.name}' 로 해석됨. "
                f"config 의 id_map_file 과 실제 파일 위치를 확인할 것)"
            )
            return {}
        with open(map_path, "r", encoding="utf-8") as _f:
            _raw = yaml.safe_load(_f) or {}

        # 옛 형식은 키가 부품명 (문자열)
        if _raw and not str(next(iter(_raw))).lstrip("-").isdigit():
            raise ValueError(
                f"{map_path}: 옛 형식({{name: {{class_id, category_id}}}})이다. "
                f"호출번호를 키로 하고 class_id 를 필드로 두는 형식으로 마이그레이션할 것 "
                f"(tools/migrate_id_map.py)."
            )

        _by_name: dict[str, tuple[int, int]] = {}
        for _e in _raw.values():
            _cid = int(_e["class_id"])                    # 라벨 정본
            _name, _kid = str(_e["name"]), int(_e.get("category_id", -1))
            self.class_map[_cid] = (_name, _kid)
            _by_name[_name] = (_cid, _kid)

        if _raw:
            _keys = [int(_k) for _k in _raw]
            if max(_keys) + 1 != len(_raw):
                print(
                    f"[WARN] {map_path}: 마지막 호출번호 {max(_keys)} 인데 항목이 "
                    f"{len(_raw)}개다. 번호가 건너뛰었거나 항목이 누락됐다."
                )
        return _by_name

    def _Auto_id_map(self, root: Path) -> dict[str, tuple[int, int]]:
        """하위 폴더명 (정렬) -> `(index, -1)`."""
        _names = sorted(d.name for d in root.iterdir() if d.is_dir())
        return {n: (i, -1) for i, n in enumerate(_names)}

