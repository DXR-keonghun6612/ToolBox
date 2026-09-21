from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, ClassVar
from dataclasses import dataclass, field

from python_toolbox.project import Base_Config


@dataclass
class Accumulator_Config(Base_Config):
    """Accumulator 하나의 Config.

    Attributes:
        config_type: `CFGS` 조회 키.
        object_type: `ACCUMULATORS` 조회 키.
        acc_kwargs: Accumulator 생성자 인자. `Extract()` 에서 언패킹.
    """

    __unpack_extract__: ClassVar[set[str]] = {"acc_kwargs"}
    __exclude_extract__: ClassVar[set[str]] = {"config_type", "object_type"}

    config_type: str = "Accumulator_Config"
    object_type: str = ""
    acc_kwargs: dict[str, Any] = field(default_factory=dict)


class Accumulator(ABC):
    """batch 결과를 스트리밍 누적하는 stateful 객체. 누적은 batch 도착 순서 무관."""

    @abstractmethod
    def Update(self, **output: Any) -> None:
        """`_Forward` 출력 전체를 받아 필요한 키만 누적."""

    @abstractmethod
    def Finalize(self) -> Any:
        """누적 state -> 확정값."""

    @abstractmethod
    def Reset(self) -> None:
        """누적 state 초기화."""


@dataclass
class Assemble_Metric_Config(Base_Config):
    """`Assemble_Metric` Config.

    Attributes:
        sub_metric_meta: `{이름: Accumulator_Config raw dict}`.
    """

    sub_metric_meta: dict[str, dict[str, Any]] = field(default_factory=dict)


class Assemble_Metric:
    """mode 하나의 Accumulator 묶음. `Update` / `Finalize` / `Reset` 을 전부에 일괄 적용."""

    def __init__(self, accs: dict[str, Accumulator]) -> None:
        self._accs = accs

    def Update(self, **output: Any) -> None:
        for _acc in self._accs.values():
            _acc.Update(**output)

    def Finalize(self) -> dict[str, Any]:
        """`{이름: 확정값}`."""
        return {_name: _acc.Finalize() for _name, _acc in self._accs.items()}

    def Reset(self) -> None:
        for _acc in self._accs.values():
            _acc.Reset()

    def __getitem__(self, key: str) -> Accumulator:
        return self._accs[key]

    def __contains__(self, key: str) -> bool:
        return key in self._accs