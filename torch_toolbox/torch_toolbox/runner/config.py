"""torch job 설정 - 학습 job(`Torch_Config` - 장치, 반복, mode 별 데이터)과 export job(`Export_Job_Config` - 끝난 학습 run 에서 빼냄).

둘 다 python_toolbox `Job_Config` 파생 - launcher meta 의 job 설정. 한 meta 에 섞이므로 `config_type` 으로 `CONFIGS` 에서 고름.
학습 job 의 하위 설정(model, loss, optim)은 사용처가 상속해 더함 - 그것도 job 설정 아래.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from python_toolbox.config import CONFIGS, Base_Config
from python_toolbox.run.job import Job_Config

from ..dataloader.definition import Dataloader_Config

#: export 가 받는 TensorRT 추론 정밀도.
PRECISIONS = ("FP32", "FP16", "INT8")


@dataclass
class Mode_Config(Base_Config):
    """mode(`train` / `val` / `test`) 하나의 데이터와 지표.

    Attributes:
        use_grad: 기울기를 쓰나. `train` mode 에서만 참으로 다룸.
        loader: DataLoader 설정.
        metric: `{이름: Accumulator_Config raw dict}` - `Assemble_Metric_Config.sub_metric_meta`.
        batch_monitoring: 배치마다 진행 막대에 보일 accumulator 이름.
    """

    use_grad: bool = False
    loader: Dataloader_Config = field(default_factory=Dataloader_Config)
    metric: dict[str, dict[str, Any]] = field(default_factory=dict)
    batch_monitoring: list[str] = field(default_factory=list)


@dataclass
class Export_Config(Base_Config):
    """ONNX export 옵션.

    Attributes:
        precision: TensorRT 추론 정밀도 - `PRECISIONS`.
        opset_version: ONNX opset.
        do_constant_folding: 상수 폴딩.
        size_mb: TensorRT workspace(MB).
        external_data: 가중치를 `.onnx.data` 로 분리. 거짓이어도 2GB 넘으면 torch 가 분리.
    """

    precision: str = "FP32"
    opset_version: int = 21
    do_constant_folding: bool = True
    size_mb: int = 4096
    external_data: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.precision not in PRECISIONS:
            raise ValueError(f"export.precision: {self.precision} not in {PRECISIONS}")


@dataclass
class Torch_Config(Job_Config):
    """학습 job 설정의 부모. 실행 값(반복 수, 장치, 주소, 가중치 고르기, test)은 정체성 밖 - 바꿔도 이어서 함.

    Attributes:
        max_iters: 최대 iteration.
        save_interval: 체크포인트 저장 주기(iteration).
        gpus: GPU 번호. 둘 이상이면 DDP. 비면 안 됨 - CPU 실행 없음.
        host_name, port_num: DDP 주소.
        world_size: 전체 분산 프로세스 수(여러 노드).
        node_rank_offset: 이 노드의 rank 시작.
        weight_path: 가중치 파일. 비면 없음. `resume` 이 있으면 무시.
        start_iter: 복원할 iteration. 없으면 job 의 선택 규칙, 그것도 없으면 마지막.
        test: learning job 이 학습 대신 test mode 만 돎.
        use_amp: AMP.
        max_grad_norm: 기울기 L2 norm 상한. 0 이면 안 자름.
        mode: mode 이름(`train` / `val` / `test`) -> 데이터와 지표.
    """

    __exclude_identity__: ClassVar[set[str]] = {
        "max_iters", "save_interval", "gpus", "host_name", "port_num", "world_size", "node_rank_offset",
        "weight_path", "start_iter", "test",
    }

    max_iters: int = 50
    save_interval: int = 1
    gpus: list[int] = field(default_factory=lambda: [0])
    host_name: str = "localhost"
    port_num: int = 12355
    world_size: int = 1
    node_rank_offset: int = 0
    weight_path: str = ""
    start_iter: int | None = None
    test: bool = False
    use_amp: bool = True
    max_grad_norm: float = 0.0
    mode: dict[str, Mode_Config] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.gpus:
            raise ValueError("gpus is empty - no CPU run")
        if self.world_size < len(self.gpus):
            raise ValueError(f"world_size {self.world_size} is smaller than local gpus {len(self.gpus)}")


@CONFIGS.Register_module("export_job_Config")
@dataclass
class Export_Job_Config(Job_Config):
    """export job 설정 - 끝난 학습 run 하나에서 모델을 빼냄. 학습 설정은 그 run 에 남은 것을 읽음.

    Attributes:
        source: 끝난 학습 run 폴더. 비면 안 됨.
        gpu: export 할 GPU 번호. 정체성 밖.
        start_iter: 빼낼 iteration. 없으면 job 의 선택 규칙, 그것도 없으면 마지막.
        export: export 옵션.
    """

    source: str = ""
    gpu: int = 0
    start_iter: int | None = None
    export: Export_Config = field(default_factory=Export_Config)

    __exclude_identity__: ClassVar[set[str]] = {"gpu"}

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.source:
            raise ValueError("source is empty - export reads a finished learning run")
