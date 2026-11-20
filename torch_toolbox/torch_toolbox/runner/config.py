"""torch 실행 설정 - 장치, 반복, mode 별 데이터, export. 사용처가 상속해 model, loss, optim 같은 하위 설정을 더함."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from python_toolbox.run.runner import Runner_Config
from python_toolbox.schema import Base_Config

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
        if self.precision not in PRECISIONS:
            raise ValueError(f"export.precision: {self.precision} not in {PRECISIONS}")


@dataclass
class Torch_Config(Runner_Config):
    """torch 실행 설정의 부모.

    Attributes:
        max_iters: 최대 iteration.
        save_interval: 체크포인트 저장 주기(iteration).
        gpus: GPU 번호. 둘 이상이면 DDP. 비면 안 됨 - CPU 실행 없음.
        host_name, port_num: DDP 주소.
        world_size: 전체 분산 프로세스 수(여러 노드).
        node_rank_offset: 이 노드의 rank 시작.
        weight_path: 가중치 파일. 비면 없음. `job.resume` 이 있으면 무시.
        start_iter: 복원할 iteration. 없으면 job 의 선택 규칙, 그것도 없으면 마지막.
        test: learning job 이 학습 대신 test mode 만 돎.
        use_amp: AMP.
        max_grad_norm: 기울기 L2 norm 상한. 0 이면 안 자름.
        mode: mode 이름(`train` / `val` / `test`) -> 데이터와 지표.
        export: export job 의 옵션.
    """

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
    export: Export_Config = field(default_factory=Export_Config)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.gpus:
            raise ValueError("gpus is empty - no CPU run")
        if self.world_size < len(self.gpus):
            raise ValueError(f"world_size {self.world_size} is smaller than local gpus {len(self.gpus)}")
