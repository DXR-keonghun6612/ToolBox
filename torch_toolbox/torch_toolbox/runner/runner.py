"""torch runner - python_toolbox `Runner` 에 torch 설정 registry 만 더함. 사용처가 상속해 `config` 타입과 `JOB_REGISTRY` 를 선언."""
from __future__ import annotations

from python_toolbox.run.runner import Runner

from .. import CFGS
from .config import Torch_Config


class Torch_Runner(Runner):
    """torch 실행의 바탕. 하위 설정은 `CFGS` 에서 `config_type` 으로 고름."""

    config: Torch_Config
    CONFIG_REGISTRY = CFGS
