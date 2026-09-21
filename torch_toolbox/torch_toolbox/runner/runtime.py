from __future__ import annotations
from typing import Any, ClassVar, TypeVar, Generic
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
from datetime import timedelta

import torch
import torch.nn as nn
import torch.onnx
import torch.distributed as dist
from torch import Tensor
from torch.multiprocessing.spawn import spawn

from python_toolbox.project import Project_Template
from python_toolbox.file import Write_to

from .utils.weight import Iter_Selection, Resolve_weight_path

from .assembler import Component_Assembler

ASSEMBLER = TypeVar("ASSEMBLER", bound=Component_Assembler)
LOSS = TypeVar("LOSS")


@dataclass
class Base_Runner(Project_Template, Generic[ASSEMBLER, LOSS]):
    """분산 셋업, 프로세스 spawn, 템플릿 루프, export. 컴포넌트는 `assembler` 가.

    Attributes:
        project_name: 워크스페이스 디렉터리명.
        assembler: 컴포넌트 조립.
        max_iters: 최대 이터레이션.
        save_interval: 체크포인트 저장 주기 (iter).
        gpus: GPU 인덱스. 2 개 이상이면 DDP.
        world_size: 전체 분산 프로세스 수 (멀티 노드).
        node_rank_offset: 이 노드의 rank 시작 오프셋.
        resume_path: resume 할 워크스페이스.
        weight_path: 가중치 파일 경로.
        start_iter: 시작 이터레이션. None 이면 `resume_selection` / `eval_selection`, 그것도 None 이면 마지막.
        resume_selection: 학습 재개 시 체크포인트 선택. 하위 러너가 선언.
        eval_selection: test, export 시 체크포인트 선택. 하위 러너가 선언.
    """

    project_name: str
    assembler: ASSEMBLER
    max_iters: int = 50
    save_interval: int = 1
    gpus: list[int] = field(default_factory=lambda: [0])
    host_name: str = "localhost"
    port_num: int = 12355
    world_size: int = 1
    node_rank_offset: int = 0
    resume_path: str | None = None
    weight_path: str | None = None
    start_iter: int | None = None
    is_multi_gpu: bool = field(init=False)

    resume_selection: ClassVar[Iter_Selection | None] = None
    eval_selection: ClassVar[Iter_Selection | None] = None

    def __post_init__(self):
        super().__init__(self.project_name)
        self.is_multi_gpu = len(self.gpus) > 1

    # --- Private (코어 인프라: 오버라이딩 금지) ---

    @contextmanager
    def _Process_context(self, p_id: int, is_test: bool = False):
        """프로세스 초기화 -> yield -> 정리.

        Args:
            p_id: 로컬 프로세스 인덱스.

        Yields:
            (rank, device, iters, components, stop_tensor). stop_tensor 는 DDP 에서만, 단일 GPU 는 None.
        """
        _rank = self.node_rank_offset + p_id if self.is_multi_gpu else 0
        _normal_exit = False
        try:
            # set_device 가 init_process_group 보다 먼저
            _device_idx = self.gpus[p_id] if self.is_multi_gpu else self.gpus[0]
            _device = torch.device(f"cuda:{_device_idx}")
            torch.cuda.set_device(_device)

            if self.is_multi_gpu:
                _num_of_gpu = len(self.gpus)
                if self.world_size < _num_of_gpu:
                    raise ValueError(
                        f"[ERROR] 설정된 world_size({self.world_size})가 "
                        f"할당된 로컬 GPU 개수({_num_of_gpu})보다 작을 수 없음.")
                _rank = self.node_rank_offset + p_id
                dist.init_process_group(
                    backend="nccl",
                    init_method=f"tcp://{self.host_name}:{self.port_num}",
                    world_size=self.world_size, rank=_rank,
                    timeout=timedelta(minutes=30))
                print(f"[INFO] Distributed Env: Rank {_rank}/{self.world_size} on {_device}")
                _w_size = self.world_size
            else:
                print(f"[INFO] Single-Process: Ready on {_device}")
                _w_size = 1

            _resolved_path = Resolve_weight_path(
                self.resume_path, self.weight_path, self.workspace, self.start_iter,
                self.eval_selection if is_test else self.resume_selection,
            )
            _start_iter, _components = self.assembler(
                _device, _w_size, _rank, is_test=is_test,
                weight_path=_resolved_path,
                is_resume=self.resume_path is not None)
            _iters = (
                range(_start_iter - 1, _start_iter)
                if is_test
                else range(_start_iter, self.max_iters)
            )
            _stop_tensor = (
                torch.zeros(1, dtype=torch.int32, device=_device)
                if self.is_multi_gpu else None
            )
            yield _rank, _device, _iters, _components, _stop_tensor
            _normal_exit = True
        except Exception as e:
            if _rank == 0:
                print(f"[ERROR] Process {_rank} failed: {e}")
            raise
        finally:
            # barrier 는 정상 종료에서만
            if self.is_multi_gpu and dist.is_initialized():
                if _normal_exit:
                    dist.barrier()
                dist.destroy_process_group()
                if _rank == 0:
                    print("[INFO] Distributed process group destroyed.")

    def __Process(self, p_id: int, is_test: bool = False):
        """프로세스 루프. spawn 대상. iter 마다 `_Iter_hook` -> metric Reset -> (학습) 체크포인트, `_Should_stop`.

        Args:
            p_id: 로컬 프로세스 인덱스.
        """
        with self._Process_context(p_id, is_test=is_test) as (
            _rank, _device, _iters, _components, _stop_tensor
        ):
            for _iter in _iters:
                self._Iter_hook(
                    _iter, _device, rank=_rank, is_test=is_test, **_components)

                for _metric in _components["metric"].values():
                    _metric.Reset()

                if is_test:
                    continue

                if _rank == 0 and _iter % self.save_interval == 0:
                    self._Save_checkpoint(_iter, rank=_rank, **_components)

                # DDP 는 rank 0 이 정하고 broadcast
                if _stop_tensor is not None:
                    if _rank == 0:
                        _stop_tensor.fill_(
                            int(self._Should_stop(_iter, _components["metric"])))
                    dist.broadcast(_stop_tensor, src=0)
                    _should_stop = bool(_stop_tensor.item() == 1)
                else:
                    _should_stop = self._Should_stop(_iter, _components["metric"])

                if _should_stop:
                    if _rank == 0:
                        print(f"[INFO] Early stopping at iter {_iter}.")
                    break

    # --- Public ---

    def Run(self, is_test: bool = False):
        """진입점. `is_test` 로 학습 / 추론 분기. 다중 GPU 면 spawn."""
        self._Setup()
        _n_size = len(self.gpus)
        if not _n_size:
            raise ValueError("[ERROR] CPU 전용 실행은 지원하지 않습니다.")
        if self.is_multi_gpu:
            spawn(self.__Process, args=(is_test,), nprocs=_n_size, join=True)
        else:
            self.__Process(0, is_test)

    def Export(
        self, save_path: str | Path | None = None,
        opset_version: int = 21, do_constant_folding: bool = True,
        precision: str = "FP32", size_mb: int = 4096,
        external_data: bool = False,
        **kwargs: Any
    ):
        """ONNX export. 단일 프로세스로 실행. 산출물 `{name}.onnx`, `{name}_rt_cfg.yaml`.

        Args:
            save_path: 저장 디렉터리. None 이면 workspace.
            opset_version: ONNX opset.
            do_constant_folding: 상수 폴딩.
            precision: TensorRT 추론 정밀도 (FP32 / FP16 / INT8).
            size_mb: TensorRT workspace (MB).
            external_data: 가중치를 `.onnx.data` 로 분리. False 여도 2GB 초과면 torch 가 분리.
            **kwargs: `torch.onnx.export` 추가 인자.
        """
        self._Setup()

        if opset_version >= 25:
            print(
                f"warning. TensorRT 10.x 공식 지원은 opset_version 25 미만입니다. "
                f"현재: {opset_version}"
            )

        _was_multi, self.is_multi_gpu = self.is_multi_gpu, False
        try:
            with self._Process_context(0, is_test=True) as (
                _, _device, _, _components, _
            ):
                _save_path = Path(save_path) if save_path is not None else Path(self.workspace)
                _save_path.mkdir(exist_ok=True, parents=True)
                print(f"[INFO] ONNX Export 시작: {_device}")

                (
                    _model, _inputs, _name, _onnx_cfg, _rt_cfg
                ) = self._Prepare_export_artifacts(
                    _device, _save_path,
                    opset_version=opset_version,
                    do_constant_folding=do_constant_folding,
                    precision=precision, size_mb=size_mb,
                    external_data=external_data,
                    **_components, **kwargs,
                )

                torch.onnx.export(_model, _inputs, **_onnx_cfg)
                Write_to(_save_path / f"{_name}_rt_cfg.yaml", _rt_cfg)
                print(f"[INFO] ONNX Export 완료: {save_path}")
        finally:
            self.is_multi_gpu = _was_multi

    # --- Protected Hooks ---

    def _Setup(self) -> bool:
        """워크스페이스 초기화, assembler config 저장. 이미 됐으면 True."""
        if self._is_setup_done:
            return True

        if self.resume_path is not None:
            self.workspace = self.workspace.parent / self.resume_path

        if super()._Setup():
            return True
        self.assembler.Save_config(self.workspace)
        return False

    def _Iter_hook(
        self, current_iter: int, device: torch.device, *,
        rank: int = 0, is_test: bool = False, **components: Any
    ) -> None:
        raise NotImplementedError

    def _Forward(
        self, batch: dict[str, Any], device: torch.device, is_train: bool,
        model: Any, **kwargs: Any
    ) -> tuple[LOSS, int, dict[str, Any]]:
        raise NotImplementedError

    def _Should_stop(self, current_iter: int, metric: Any) -> bool:
        return False

    def _Save_checkpoint(
        self, current_iter: int, *, rank: int = 0, **components: Any
    ):
        raise NotImplementedError

    def _Prepare_export_artifacts(
        self, device: torch.device, save_path: Path, *,
        opset_version: int, do_constant_folding: bool,
        precision: str, size_mb: int, external_data: bool=False,
        **components: Any,
    ) -> tuple[
        nn.Module, tuple[Tensor, ...], str, dict[str, Any], dict[str, Any]
    ]:
        """ONNX export 재료. 하위 러너 구현.

        Args:
            save_path: 저장 디렉터리.
            opset_version, do_constant_folding, precision, size_mb, external_data: `Export` 인자 그대로.
            **components: `assembler()` 의 components.

        Returns:
            (export_model, dummy_inputs, name, onnx_cfg, rt_cfg).

            - export_model: export 할 `nn.Module`. 전처리 융합 포함 가능
            - dummy_inputs: `torch.onnx.export` 더미 입력
            - name: 파일명 (확장자 제외)
            - onnx_cfg: `torch.onnx.export` 인자 (`f`, `export_params`, `opset_version`, `do_constant_folding`,
              `input_names`, `output_names`, `dynamic_shapes` 등)
            - rt_cfg: `{name}_rt_cfg.yaml`. `onnx_file`, `precision`, `workspace_size_mb`,
              `input_profiles`, `output_profiles` (형식은 `Custom_Dataset.Info_for_onnx`)
        """
        raise NotImplementedError
