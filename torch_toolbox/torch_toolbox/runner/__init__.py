from __future__ import annotations
import argparse
from typing import Any
from dataclasses import fields
from pathlib import Path

from python_toolbox.file import Make_dict_from

from .runtime import Base_Runner


def Resolve_config(value: Any) -> Any:
    """config 값 해석. dict 는 값마다 재귀, `.yaml` 문자열은 파일을 dict 로 로드 (내용은 재귀 안 함), 그 외 그대로."""
    if isinstance(value, dict):
        return {_k: Resolve_config(_v) for _k, _v in value.items()}
    if isinstance(value, str) and value.endswith((".yaml", ".yml")):
        return Make_dict_from(Path(value))[1]
    return value


def Build_runner_parser() -> argparse.ArgumentParser:
    """`Base_Runner` 공통 CLI. 진입점이 runner 별 인자를 더함."""
    _p = argparse.ArgumentParser()
    _p.add_argument("--config_file",   type=str, default="conf/runtime.yaml")
    _p.add_argument("--test",          action="store_true")
    _p.add_argument("--assembler_meta", type=str, default=None)
    _p.add_argument("--project_name",  type=str, default=None)
    _p.add_argument("--max_iters",     type=int, default=None)
    _p.add_argument("--save_interval", type=int, default=None)
    _p.add_argument("--gpus",          type=int, nargs="*", default=None)
    _p.add_argument("--resume_path",   type=str, default=None)
    _p.add_argument("--weight_path",   type=str, default=None)
    _p.add_argument("--start_iter",    type=int, default=None,
                    help="복원할 iteration 을 직접 지정 (미지정 시 러너 선언에 따름)")
    _p.add_argument("--export",        type=str, nargs="?", const="FP32", default=None,
                    choices=["FP32", "FP16", "INT8"],
                    help="학습/추론 대신 ONNX export 수행 (값=TensorRT 추론 정밀도, "
                         "생략 시 FP32). 산출물은 workspace/<project>_<precision>.onnx")
    return _p


def Runtime_init(
    runner_cls: type,
    assembler_cls: type,
    *,
    config_file: str | Path,
    **hub_override: Any,
) -> Base_Runner:
    """hub YAML -> runner 인스턴스.

    hub 최상위 키 중 runner 필드명과 같은 것은 runner kwargs, `assembler_meta` 는 `Resolve_config` 뒤 assembler kwargs.

    Args:
        runner_cls: runner 클래스.
        assembler_cls: assembler 클래스.
        config_file: hub YAML 경로.
        **hub_override: YAML 값을 덮어쓰는 인자. None 은 무시.
    """
    _, _hub = Make_dict_from(Path(config_file))
    _hub.update({_k: _v for _k, _v in hub_override.items() if _v is not None})

    _runner_field_names = {f.name for f in fields(runner_cls) if f.init}
    _runner_kwargs = {_k: _v for _k, _v in _hub.items() if _k in _runner_field_names}

    _am = _hub.get("assembler_meta", {})
    if isinstance(_am, str):
        _, _am = Make_dict_from(Path(_am))
    _assembler_meta = Resolve_config(_am)

    return runner_cls(assembler=assembler_cls(**_assembler_meta), **_runner_kwargs)
