"""torch runner - python_toolbox `Runner` 에 torch 설정 registry 와 이어서 하기 허용 경로만 더함. 사용처가 상속해 `config` 타입과 `JOB_REGISTRY` 를 선언."""
from __future__ import annotations

from python_toolbox.run.runner import Runner

from .. import CFGS
from .config import Torch_Config


class Torch_Runner(Runner):
    """torch 실행의 바탕. 하위 설정은 `CFGS` 에서 `config_type` 으로 고름.

    이어서 할 때 달라도 되는 것 - 장치, 반복 수, 가중치 고르기, test 여부, export 옵션. 모델, 데이터, 손실, optim 은 같아야 함.
    """

    config: Torch_Config
    CONFIG_REGISTRY = CFGS
    RESUME_FREE = frozenset({
        "test", "max_iters", "save_interval", "gpus", "host_name", "port_num", "world_size", "node_rank_offset",
        "weight_path", "start_iter", "export",
    })
