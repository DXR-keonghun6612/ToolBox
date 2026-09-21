from __future__ import annotations
from typing import Any, cast

from python_toolbox.registry import Registry

from .. import CFGS
from .definition import Composable_Config, Composable_Module, Module_Config_Template
from .model.definition import Trainable_Model, Trainable_Model_Config
from .model.backbone import BACKBONES, BACKBONE_CFGS
from .loss.definition import Assemble_Loss_Config, Assemble_Loss


MODULES_CONFIG = (
    Module_Config_Template
    | Assemble_Loss_Config
    | Trainable_Model_Config | BACKBONE_CFGS
)
MODULES = (
    Composable_Module
    | Assemble_Loss
    | Trainable_Model | BACKBONES
)


def _Resolve_term(term: Any, built: dict[str, Any], context: dict[str, Any] | None) -> int:
    """차원 표현식의 항 하나 -> 정수.

    지원 형태::

        768              상수
        "$feat_dim"      context 값
        "backbone"       같은 계층에서 먼저 만들어진 모듈의 `Out_channels()[-1]`
        "backbone[0]"    특정 출력 단
    """
    if isinstance(term, int):
        return term
    if not isinstance(term, str):
        raise TypeError(f"차원 표현식 항은 int 또는 str이어야 한다: {term!r}")

    if term.startswith("$"):
        _key = term[1:]
        if not context or _key not in context:
            raise KeyError(
                f"차원 표현식이 context['{_key}']를 참조하는데 주입되지 않았다. "
                f"assembler의 _Build_context()가 이 키를 채우는지 확인할 것. "
                f"(현재 context 키: {sorted(context) if context else []})"
            )
        return int(context[_key])

    _name, _, _rest = term.partition("[")
    _idx = int(_rest.rstrip("]")) if _rest else -1
    if _name not in built:
        raise KeyError(
            f"차원 표현식이 '{_name}'을 참조하는데 같은 계층에서 아직 만들어지지 않았다. "
            f"sub_module_meta에서 '{_name}'이 참조하는 쪽보다 **먼저** 선언되어야 한다. "
            f"(현재까지 만들어진 것: {sorted(built)})"
        )
    return int(built[_name].Out_channels()[_idx])


def _Resolve_value(value: Any, built: dict[str, Any], context: dict[str, Any] | None) -> Any:
    """meta 값 하나 해석. dict / list 안은 재귀, 그 외 값은 그대로.

    지원 형태::

        {"sum": [...]}   항의 합 (정수)
        "$key"           context 값 그대로 (타입 제한 없음)
    """
    if isinstance(value, dict) and set(value) == {"sum"}:
        return sum(_Resolve_term(_t, built, context) for _t in value["sum"])
    if isinstance(value, str) and value.startswith("$"):
        _key = value[1:]
        if not context or _key not in context:
            raise KeyError(
                f"config가 context['{_key}']를 참조하는데 주입되지 않았다. "
                f"assembler의 _Build_context()가 이 키를 채우는지 확인할 것. "
                f"(현재 context 키: {sorted(context) if context else []})"
            )
        return context[_key]
    if isinstance(value, dict):
        return {_k: _Resolve_value(_v, built, context) for _k, _v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_Resolve_value(_v, built, context) for _v in value)
    return value


def _Resolve_meta(
    meta: dict[str, Any], built: dict[str, Any], context: dict[str, Any] | None
) -> dict[str, Any]:
    """meta 의 각 값을 `_Resolve_value` 로 해석한 새 dict. 원본은 안 바꿈."""
    return {_k: _Resolve_value(_v, built, context) for _k, _v in meta.items()}


def Build_from_registry(
    config: MODULES_CONFIG, registry: Registry, context: dict[str, Any] | None = None,
) -> MODULES:
    """Config 트리 재귀 조립.

    `Composable_Config` 면 `sub_module_meta` 를 선언 순서대로 빌드해 부모 `Build(**sub_modules)` 에 주입.
    뒤 형제의 차원 표현식은 앞 형제의 `Out_channels()` 와 `context` 로 해석
    (예 `in_channels: {sum: [backbone, $feat_dim]}`).

    Args:
        config: 빌드할 모듈의 Config.
        registry: 대상 도메인 registry (`MODELS`, `LOSSES` 등).
        context: 조립 밖에서 오는 값 (예 `{"feat_dim": 695}`). `$키` 로 참조.

    Returns:
        조립된 `Composable_Module`.
    """
    _sub_kwargs = {}

    if isinstance(config, Composable_Config):
        for _k, _meta in config.sub_module_meta.items():
            _meta = _Resolve_meta(_meta, _sub_kwargs, context)
            _sub_cfg = cast(Composable_Config, CFGS.Get(_meta["config_type"])(**_meta))
            _sub_kwargs[_k] = Build_from_registry(_sub_cfg, registry, context)

    return registry.Get(config.object_type)(**config.Extract(), **_sub_kwargs)