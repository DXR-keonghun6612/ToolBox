from __future__ import annotations
from typing import Any, TypeVar, Generic
from dataclasses import dataclass, field, InitVar
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torch.amp.grad_scaler import GradScaler

from python_toolbox.project import Build_config
from python_toolbox.file import Write_to

from .. import CFGS, Mode
from ..dataloader.definition import Dataloader_Config
from ..dataloader.build import Build_dataloader
from ..metric.definition import Assemble_Metric_Config, Assemble_Metric
from ..metric.build import Build_metric

MODEL = TypeVar("MODEL")
OPTIM = TypeVar("OPTIM")
SCHEDULER = TypeVar("SCHEDULER")


@dataclass
class Component_Assembler(Generic[OPTIM, SCHEDULER, MODEL]):
    """파이프라인 컴포넌트 조립 기반 클래스.

    mode_meta 구조: ``{mode_str: {use_grad, loader, metric, batch_monitoring}}``.
    meta는 그대로 보유하고 build 시점에 Config·DataLoader·metric으로 변환된다.
    서브클래스는 ``_Build``에서 도메인별 컴포넌트(model·loss·optim)를 추가한다.

    Attributes:
        shared: 모든 Config에 공통 적용되는 기반 필드.
        use_amp: AMP(자동 혼합 정밀도) 활성화 여부.
        max_grad_norm: 그래디언트 L2 norm 상한. 0 이면 자르지 않는다.
            unscale 뒤에 걸므로 AMP 와 같이 써도 스케일 인자에 영향받지 않는다.
            잘리기 전 norm 이 ``grad_norm`` 으로 배치 metric 에 실린다 — 상한에 걸리는
            빈도가 높으면 lr 이 과한 것이고, 그건 이 값이 아니라 lr 로 고친다.
        mode_cfg: mode 문자열 → 처리된 meta dict 매핑.
    """

    shared: dict[str, Any] = field(default_factory=dict)
    use_amp: bool = True
    max_grad_norm: float = 0.0

    mode_meta: InitVar[dict[str, dict[str, Any]] | None] = None

    mode_cfg: dict[str, dict[str, Any]] = field(init=False)

    def __post_init__(
        self,
        mode_meta: dict[str, dict[str, Any]] | None,
    ) -> None:
        # mode_meta에 선언된 mode만 보유; use_grad는 TRAIN에서만 활성화
        self.mode_cfg = {
            _k.value: {**_v, "use_grad": bool(_v.get("use_grad", False)) and _k == Mode.TRAIN}
            for _k in Mode
            if mode_meta and _k.value in mode_meta
            for _v in (mode_meta[_k.value],)
        }

    def Save_config(self, save_dir: str | Path, **kwarg) -> None:
        """조립 설정 전체를 YAML로 직렬화하여 저장한다.

        서브클래스는 **kwarg로 추가 항목을 병합한다.

        Args:
            save_dir: 저장 디렉터리 경로.
            **kwarg: 서브클래스 추가 직렬화 항목 (model_cfg, loss_cfg 등).
        """
        _data: dict[str, Any] = {
            "shared": self.shared,
            "use_amp": self.use_amp,
            "max_grad_norm": self.max_grad_norm,
            "mode_cfg": dict(self.mode_cfg),
            **kwarg,
        }
        Write_to(Path(save_dir) / "config.yaml", _data)

    def __call__(
        self,
        device: torch.device,
        world_size: int,
        rank: int,
        is_test: bool = False,
        weight_path: str | None = None,
        is_resume: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        """컴포넌트를 조립하고 가중치를 로드한 뒤 ``(start_iter, components)``를 반환한다.

        Args:
            device: 타깃 디바이스.
            world_size: 분산 프로세스 수.
            rank: 현재 프로세스 rank.
            is_test: True이면 model·dataloader·metric만 조립 (optim 제외).
            weight_path: 로드할 가중치 경로. None이면 scratch 학습.
            is_resume: True이면 학습 상태(optim·scheduler·scaler)도 복원.

        Returns:
            tuple: (start_iter, components dict)
        """
        _components = self._Build(device, world_size, rank, is_test)
        # 가중치 로드 → 체크포인트에서 시작 이터레이션 결정
        _start_iter = self._Load_model_weights(weight_path, is_resume, **_components)

        if not is_test and is_resume:
            # resume: 옵티마이저·스케줄러·스케일러 상태 복원
            self._Restore_train_states(weight_path, _start_iter, **_components)

        return _start_iter, _components

    # --- 서브클래스 구현 지점 ---

    def _Build(
        self, device: torch.device, world_size: int, rank: int,
        is_test: bool = False,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _Build_model(
        self, device: torch.device, world_size: int,
        context: dict[str, Any] | None = None,
    ) -> MODEL:
        raise NotImplementedError

    # --- 공통 빌드 헬퍼 ---

    def _Build_mode_data(
        self, is_test: bool, world_size: int, rank: int,
    ) -> tuple[dict, dict, dict]:
        """활성 mode별로 dataset·dataloader·metric을 일괄 조립한다.

        is_test이면 TEST만, 아니면 TRAIN·VALIDATION을 순회한다.
        mode_cfg에 선언되지 않은 mode는 silently skip된다.

        Args:
            is_test: True이면 TEST mode 전용.
            world_size: DDP 프로세스 수 (DistributedSampler 결정에 사용).
            rank: 현재 프로세스 rank.

        Returns:
            tuple: (datasets, dataloaders, metric) — 각각 Mode 키 dict.
        """
        _modes = [Mode.TEST] if is_test else [Mode.TRAIN, Mode.VALIDATION]
        _datasets: dict[Mode, Any] = {}
        _dataloaders: dict[Mode, tuple[bool, DataLoader]] = {}
        _metric: dict[Mode, Assemble_Metric] = {}
        for _mode in _modes:
            if _mode.value not in self.mode_cfg:
                continue
            _meta = self.mode_cfg[_mode.value]
            # meta dict → Dataloader_Config → dataset + DataLoader
            _loader_cfg = Build_config(Dataloader_Config, CFGS, _meta.get("loader", {}), **self.shared)
            _dataset, _loader = Build_dataloader(_loader_cfg, _mode, world_size, rank)
            _datasets[_mode] = _dataset
            _dataloaders[_mode] = (_meta["use_grad"], _loader)
            _metric[_mode] = Build_metric(Assemble_Metric_Config(sub_metric_meta=_meta.get("metric", {})))
        return _datasets, _dataloaders, _metric

    def _Build_loss(self, device: torch.device) -> Any:
        raise NotImplementedError

    def _Build_optim_and_scheduler(
        self, model: MODEL,
    ) -> tuple[OPTIM, SCHEDULER, GradScaler]:
        raise NotImplementedError

    def _Load_model_weights(
        self, weight_path: str | None, is_resume: bool, **components: Any,
    ) -> int:
        return 0

    def _Restore_train_states(
        self, weight_path: str | None, start_iter: int, **components: Any,
    ) -> None:
        pass
