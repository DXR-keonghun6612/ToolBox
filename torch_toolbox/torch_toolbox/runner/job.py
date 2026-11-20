"""torch job - 프로세스 문맥(장치, DDP, 조립, 가중치)을 바탕에 두고, learning(train / val / test)과 export 가 그 위에.

GPU 가 둘 이상이면 learning 은 GPU 마다 프로세스를 띄움 - 자식은 `(job 클래스, 설정, 결과 자리)` 로 job 을 다시 지음.
자식의 기록은 rank 0 만 설정의 `log` 대로, 나머지는 stderr 의 WARNING 이상만. 자식의 실패는 예외로 부모에 올라와 실패로 셈.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.onnx
from torch import Tensor
from torch.multiprocessing.spawn import spawn

from python_toolbox.file import Write_to
from python_toolbox.run.job import Job
from python_toolbox.run.log import CONSOLE, Log_Config, Setup_log

from .assembler import Component_Assembler
from .config import Export_Config, Torch_Config
from .utils.weight import Iter_Selection, Resolve_weight_path


class Torch_Job(Job):
    """torch job 의 바탕 - 프로세스 하나의 문맥. 하위가 `Assembler` 와 체크포인트 선택을 선언.

    Attributes:
        config: runner 가 지은 torch 설정.
    """

    config: Torch_Config
    #: 프로세스마다 컴포넌트를 짓는 클래스.
    Assembler: ClassVar[type[Component_Assembler]] = Component_Assembler
    #: 이어서 학습할 때 체크포인트 선택. 없으면 마지막.
    resume_selection: ClassVar[Iter_Selection | None] = None
    #: test, export 때 체크포인트 선택. 없으면 마지막.
    eval_selection: ClassVar[Iter_Selection | None] = None

    @property
    def is_multi_gpu(self) -> bool:
        """GPU 가 둘 이상 - DDP."""
        return len(self.config.gpus) > 1

    @contextmanager
    def _Process_context(self, p_id: int, is_test: bool = False, multi: bool | None = None):
        """프로세스 준비 -> yield -> 정리.

        Args:
            p_id: 이 노드 안의 프로세스 번호.
            is_test: 참이면 optim 없이, 체크포인트는 `eval_selection`.
            multi: DDP 로 돌지. 없으면 `is_multi_gpu`.

        Yields:
            (rank, device, iters, components, stop_tensor). stop_tensor 는 DDP 에서만, 아니면 None.
        """
        _cfg = self.config
        _multi = self.is_multi_gpu if multi is None else multi
        _rank = _cfg.node_rank_offset + p_id if _multi else 0
        _normal_exit = False
        try:
            # set_device 가 init_process_group 보다 먼저
            _device = torch.device(f"cuda:{_cfg.gpus[p_id] if _multi else _cfg.gpus[0]}")
            torch.cuda.set_device(_device)
            if _multi:
                dist.init_process_group(
                    backend="nccl", init_method=f"tcp://{_cfg.host_name}:{_cfg.port_num}",
                    world_size=_cfg.world_size, rank=_rank, timeout=timedelta(minutes=30))
                self.log.info("distributed process ready",
                              extra={"rank": _rank, "world_size": _cfg.world_size, "device": str(_device)})
                _w_size = _cfg.world_size
            else:
                self.log.info("single process ready", extra={"device": str(_device)})
                _w_size = 1

            _weight = Resolve_weight_path(
                bool(_cfg.resume), _cfg.weight_path or None, self.result_dir, _cfg.start_iter,
                self.eval_selection if is_test else self.resume_selection,
            )
            _start_iter, _components = self.Assembler(_cfg)(
                _device, _w_size, _rank, is_test=is_test, weight_path=_weight, is_resume=bool(_cfg.resume))
            _iters = range(_start_iter - 1, _start_iter) if is_test else range(_start_iter, _cfg.max_iters)
            _stop_tensor = torch.zeros(1, dtype=torch.int32, device=_device) if _multi else None
            yield _rank, _device, _iters, _components, _stop_tensor
            _normal_exit = True
        finally:
            # barrier 는 정상 끝에서만
            if _multi and dist.is_initialized():
                if _normal_exit:
                    dist.barrier()
                dist.destroy_process_group()


class Learning_Job(Torch_Job):
    """학습과 검증, 또는 `config.test` 면 test mode 만. 하위가 iteration 갈고리를 구현."""

    def Work(self) -> None:
        """GPU 가 둘 이상이면 GPU 마다 프로세스, 아니면 이 프로세스에서."""
        _is_test = self.config.test
        if self.is_multi_gpu:
            spawn(_Spawned, args=(type(self), self.config, self.result_dir, _is_test),
                  nprocs=len(self.config.gpus), join=True)
        else:
            self._Process(0, _is_test)

    def _Process(self, p_id: int, is_test: bool) -> None:
        """프로세스 하나의 반복. iteration 마다 `_Iter_hook` -> metric `Reset` -> (학습) 체크포인트, `_Should_stop`."""
        with self._Process_context(p_id, is_test=is_test) as (_rank, _device, _iters, _components, _stop_tensor):
            for _iter in _iters:
                self._Iter_hook(_iter, _device, rank=_rank, is_test=is_test, **_components)

                for _metric in _components["metric"].values():
                    _metric.Reset()

                if is_test:
                    continue

                if _rank == 0 and _iter % self.config.save_interval == 0:
                    self._Save_checkpoint(_iter, rank=_rank, **_components)

                # DDP 는 rank 0 이 정해 broadcast
                if _stop_tensor is not None:
                    if _rank == 0:
                        _stop_tensor.fill_(int(self._Should_stop(_iter, _components["metric"])))
                    dist.broadcast(_stop_tensor, src=0)
                    _should_stop = bool(_stop_tensor.item() == 1)
                else:
                    _should_stop = self._Should_stop(_iter, _components["metric"]) or self.stopped

                if _should_stop:
                    self.log.info("early stop", extra={"iter": _iter})
                    break

    # --- 하위 구현 자리 ---

    def _Iter_hook(
        self, current_iter: int, device: torch.device, *,
        rank: int = 0, is_test: bool = False, **components: Any
    ) -> None:
        raise NotImplementedError

    def _Should_stop(self, current_iter: int, metric: Any) -> bool:
        return False

    def _Save_checkpoint(self, current_iter: int, *, rank: int = 0, **components: Any) -> None:
        raise NotImplementedError


class Export_Job(Torch_Job):
    """ONNX export - 프로세스 하나. 산출물은 결과 자리의 `{name}.onnx`, `{name}_rt_cfg.yaml`. 하위가 재료를 구현."""

    def Work(self) -> None:
        _export = self.config.export
        if _export.opset_version >= 25:
            self.log.warning("TensorRT 10.x supports opset below 25", extra={"opset_version": _export.opset_version})

        with self._Process_context(0, is_test=True, multi=False) as (_, _device, _, _components, _):
            _model, _inputs, _name, _onnx_cfg, _rt_cfg = self._Prepare_export_artifacts(
                _device, self.result_dir, _export, **_components)
            torch.onnx.export(_model, _inputs, **_onnx_cfg)
            Write_to(self.result_dir / f"{_name}_rt_cfg.yaml", _rt_cfg)
            self.log.info("onnx exported", extra={"onnx_name": _name, "precision": _export.precision})

    def _Prepare_export_artifacts(
        self, device: torch.device, save_path: Path, export: Export_Config, **components: Any,
    ) -> tuple[nn.Module, tuple[Tensor, ...], str, dict[str, Any], dict[str, Any]]:
        """ONNX export 재료. 하위 구현.

        Args:
            save_path: 저장 폴더 - 결과 자리.
            export: export 옵션.
            **components: assembler 가 지은 컴포넌트.

        Returns:
            (export_model, dummy_inputs, name, onnx_cfg, rt_cfg).

            - export_model: export 할 `nn.Module`. 전처리 융합 가능
            - dummy_inputs: `torch.onnx.export` 의 더미 입력
            - name: 파일 이름(확장자 없이)
            - onnx_cfg: `torch.onnx.export` 인자(`f`, `export_params`, `opset_version`, `do_constant_folding`,
              `input_names`, `output_names`, `dynamic_shapes` 등)
            - rt_cfg: `{name}_rt_cfg.yaml` 내용. `onnx_file`, `precision`, `workspace_size_mb`, `input_profiles`,
              `output_profiles`(형식은 `Custom_Dataset.Info_for_onnx`)
        """
        raise NotImplementedError


def _Spawned(p_id: int, job_cls: type[Learning_Job], config: Torch_Config, result_dir: Path, is_test: bool) -> None:
    """DDP 자식 프로세스 하나 - job 을 다시 짓고 기록을 걸고 반복. spawn 대상이라 모듈 함수."""
    if config.node_rank_offset + p_id == 0:
        Setup_log(result_dir, config.log)
    else:
        Setup_log(None, {"root": Log_Config(level="WARNING", to=[CONSOLE])})
    job_cls(config, result_dir)._Process(p_id, is_test)
