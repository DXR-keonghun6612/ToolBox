from __future__ import annotations
from typing import Any, Callable
from contextlib import nullcontext

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import torch.optim as optim
from torch.amp.grad_scaler import GradScaler

from python_toolbox.system import Time_Utils

from ... import Mode
from ..utils.log import log_batch, log_iter
from ...modules.model.definition import Trainable_Model
from ...metric.definition import Assemble_Metric
from ..runtime import Base_Runner
from .assembler import Supervised_Assembler


LOSS_FN = Callable[
    [dict[str, Any], dict[str, Any]],
    tuple[torch.Tensor, dict[str, float]]
]


class Supervised_Runner(Base_Runner[Supervised_Assembler, torch.Tensor | None]):
    """지도학습 파이프라인의 구체화 러너.

    _Iter_hook은 고정 구현됨.
    서브클래스는 _Forward만 override하여 task별 forward 로직을 정의한다.
    """

    def _Iter_hook(
        self,
        current_iter: int,
        device: torch.device,
        *,
        rank: int = 0,
        is_test: bool = False,
        model: Trainable_Model,
        dataloaders: dict[Mode, tuple[bool, DataLoader]],
        loss_fn: LOSS_FN | None = None,
        optimizer: optim.Optimizer | None = None,
        scheduler: optim.lr_scheduler.LRScheduler | None = None,
        scaler: GradScaler | None = None,
        metric: dict[Mode, Assemble_Metric],
        **kwargs: Any,
    ) -> None:
        """단일 iter에서 모든 mode를 순회하며 forward·backward·metric 갱신을 수행한다.

        _Iter_context가 model 상태와 grad 컨텍스트를 관리하며,
        각 batch에 대해 _Forward → metric.Update → backward 순으로 실행된다.

        Args:
            current_iter: 현재 이터레이션 인덱스.
            device: 타깃 디바이스.
            rank: 현재 프로세스 rank (로그 출력 제어용).
            is_test: True이면 backward 없이 추론만 수행.
            model: 대상 모델.
            dataloaders: mode → (use_grad, DataLoader) 매핑.
            loss_fn: loss 함수. is_test이면 None 허용.
            optimizer: 파라미터 업데이트 옵티마이저.
            scheduler: 학습률 스케줄러.
            scaler: AMP GradScaler.
            metric: mode별 평가 지표 accumulator.
            **kwargs: _Forward에 그대로 전달되는 추가 인자.
        """
        _use_amp = self.assembler.use_amp
        _max_norm = self.assembler.max_grad_norm
        for _mode, _loader, _is_train in self._Iter_context(
            current_iter, dataloaders, model, scheduler, is_test, rank, metric
        ):
            _total = len(_loader)
            for _i, _batch in enumerate(_loader):
                _t_st = Time_Utils.Stamp()
                with torch.autocast(device_type=device.type, enabled=_use_amp):
                    _loss, _batch_size, _output = self._Forward(
                        _batch, device, _is_train, model, loss_fn=loss_fn, **kwargs
                    )

                if _is_train and _loss is not None:
                    assert optimizer is not None and scaler is not None
                    optimizer.zero_grad(set_to_none=True)
                    scaler.scale(_loss).backward()
                    if _max_norm > 0:
                        # unscale 뒤에 잘라야 AMP 스케일 인자와 무관한 실제 norm 기준이 된다.
                        scaler.unscale_(optimizer)
                        _norm = torch.nn.utils.clip_grad_norm_(
                            model.parameters(), _max_norm)
                        # 잘리기 전 norm. 상한에 얼마나 자주 걸리는지가 lr 진단이다.
                        _output["grad_norm"] = (float(_norm), _batch_size)
                    scaler.step(optimizer)
                    scaler.update()

                # 경과 시간은 batch_size로 나눠 sample당 시간으로 정규화
                _elapsed = (Time_Utils.Stamp() - _t_st).total_seconds()
                if _mode in metric:
                    metric[_mode].Update(
                        time=(_elapsed / _batch_size, _batch_size), **_output
                    )

                _batch_mon = self.assembler.mode_cfg[_mode.value].get("batch_monitoring")
                if _batch_mon and _mode in metric:
                    log_batch(current_iter, _i, _total, metric[_mode], _batch_mon)

    def _Iter_context(
        self,
        current_iter: int,
        dataloaders: dict[Mode, tuple[bool, DataLoader]],
        model: nn.Module,
        scheduler: optim.lr_scheduler.LRScheduler | None,
        is_test: bool,
        rank: int = 0,
        metric: dict[Mode, Assemble_Metric] | None = None,
    ):
        """mode별 model 상태·grad 컨텍스트를 관리하는 generator.

        모든 mode를 소진한 뒤 scheduler.step → log_iter 순으로 실행된다.
        finally는 generator close/throw 시에도 scheduler.step을 보장한다.

        Yields:
            tuple: (mode, loader, is_train)
        """
        try:
            for _mode, (_use_grad, _loader) in dataloaders.items():
                _is_train = _use_grad and not is_test
                model.train() if _is_train else model.eval()
                with nullcontext() if _is_train else torch.no_grad():
                    yield _mode, _loader, _is_train
        finally:
            # 조기 종료나 예외 시에도 scheduler.step은 반드시 실행
            if not is_test and scheduler is not None:
                scheduler.step()
        if rank == 0 and metric is not None:
            log_iter(
                current_iter,
                {_m.value: _a.Finalize() for _m, _a in metric.items()},
                self.workspace,
            )

    def _Forward(
        self,
        batch: dict[str, Any],
        device: torch.device,
        is_train: bool,
        model: nn.Module,
        **kwargs: Any,
    ) -> tuple[torch.Tensor | None, int, dict[str, Any]]:
        raise NotImplementedError

    def _Should_stop(
        self, current_iter: int, metric: dict[Mode, Assemble_Metric]
    ) -> bool:
        return False

    def _Save_checkpoint(
        self,
        current_iter: int,
        *,
        rank: int = 0,
        model: Trainable_Model,
        optimizer: optim.Optimizer,
        scheduler: optim.lr_scheduler.LRScheduler | None,
        scaler: GradScaler,
        **kwargs: Any,
    ) -> None:
        """현재 iter의 학습 상태를 체크포인트로 저장한다.

        DDP 모델은 .module에서 실제 가중치를 추출한다.
        scheduler가 None이면 scheduler_state를 저장하지 않는다.

        Args:
            current_iter: 저장할 이터레이션 인덱스.
            rank: 현재 프로세스 rank (rank 0만 저장).
            model: 저장할 모델.
            optimizer: 저장할 옵티마이저.
            scheduler: 저장할 스케줄러. None이면 생략.
            scaler: 저장할 AMP GradScaler.
            **kwargs: 사용되지 않는 컴포넌트 (무시됨).
        """
        # DDP 래퍼 벗기기: state_dict는 원본 모듈에서 추출
        _target = (
            model.module
            if isinstance(model, nn.parallel.DistributedDataParallel)
            else model
        )
        _checkpoint: dict[str, Any] = {
            "iter": current_iter,
            "model_state": _target.state_dict(),
            "optim_state": optimizer.state_dict(),
            "scaler_state": scaler.state_dict(),
        }
        if scheduler is not None:
            _checkpoint["scheduler_state"] = scheduler.state_dict()

        _save_dir = self.workspace / "checkpoints"
        _save_dir.mkdir(parents=True, exist_ok=True)
        torch.save(_checkpoint, _save_dir / f"checkpoint_{current_iter}.pt")

