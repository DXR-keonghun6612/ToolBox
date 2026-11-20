"""가중치 파일 고르기 - 이어서 하기면 결과 자리의 체크포인트에서, 아니면 지정한 파일. 체크포인트 iteration 은 지정, 선택 규칙, 마지막 차례."""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from python_toolbox.file import Read_from

SELECT_RULE = Callable[[Mapping[int, float]], int]    #: `{iter: 점수}` -> iter

_log = logging.getLogger(__name__)


def Max_of(scores: Mapping[int, float]) -> int:
    """점수 최대 iteration. 같으면 나중 것."""
    return max(sorted(scores, reverse=True), key=lambda _k: scores[_k])


def Min_of(scores: Mapping[int, float]) -> int:
    """점수 최소 iteration. 같으면 나중 것."""
    return min(sorted(scores, reverse=True), key=lambda _k: scores[_k])


@dataclass(frozen=True)
class Iter_Selection:
    """되살릴 iteration 고르기. job 이 `ClassVar` 로 선언.

    Attributes:
        rule: `SELECT_RULE`. 예 `Min_of`, `Max_of`.
        mode: 기록 mode(`train` / `val` 등).
        metric: 지표 이름(`accuracy` / `loss` 등).
    """

    rule: SELECT_RULE
    mode: str
    metric: str

    def __call__(self, result_dir: Path) -> int:
        """학습 기록에서 iteration 고름.

        Raises:
            FileNotFoundError: 그 mode 의 기록 폴더 없음.
            ValueError: 그 지표를 가진 iteration 없음.
        """
        _scores = Read_metric_log(result_dir, self.mode, self.metric)
        _pick = self.rule(_scores)
        _log.info("checkpoint iter picked", extra={
            "iter": _pick, "rule": self.rule.__name__, "mode": self.mode, "metric": self.metric,
            "score": _scores[_pick], "candidates": len(_scores)})
        return _pick


def Read_metric_log(result_dir: Path, mode: str, metric: str) -> dict[int, float]:
    """`avg/<mode>/<acc_name>/iter_<i>.json`(`log_iter` 출력) -> `{iter: 값}`.

    Raises:
        FileNotFoundError: 그 mode 의 기록 폴더 없음.
        ValueError: 지표 없음, 또는 accumulator 여럿이 같은 이름을 냄.
    """
    _dir = result_dir / "avg" / mode
    if not _dir.exists():
        raise FileNotFoundError(f"{_dir}: no metric log - check that training ran and mode '{mode}' is right")

    _scores: dict[int, float] = {}
    _sources: set[str] = set()
    for _json in _dir.glob("*/iter_*.json"):
        _iter = _Iter_of(_json)
        if _iter is None:
            continue
        _ok, _data = Read_from(_json)
        if not _ok or not isinstance(_data, dict) or metric not in _data:
            continue
        _scores[_iter] = float(_data[metric])
        _sources.add(_json.parent.name)

    if len(_sources) > 1:
        raise ValueError(f"metric '{metric}' comes from more than one accumulator {sorted(_sources)}")
    if not _scores:
        _seen = sorted({_p.parent.name for _p in _dir.glob("*/iter_*.json")})
        raise ValueError(f"{_dir}: no metric '{metric}' - accumulators {_seen or 'none'}")
    return _scores


def Resolve_weight_path(
    is_resume: bool,
    weight_path: str | None,
    result_dir: Path,
    start_iter: int | None,
    selection: Iter_Selection | None = None,
) -> str | None:
    """가중치 파일 경로. 이어서 하기가 먼저, 다음 `weight_path`, 둘 다 없으면 None.

    Args:
        is_resume: 결과 자리가 이어서 하는 run 폴더 - `result_dir/checkpoints` 에서 찾음.
        weight_path: 가중치 파일 경로.
        result_dir: 결과 자리.
        start_iter: 지목할 iteration.
        selection: iteration 고르기.

    Raises:
        FileNotFoundError: 가중치를 요구했으나 못 찾음.
    """
    if is_resume:
        if weight_path is not None:
            _log.warning("resume and weight_path both given - weight_path ignored", extra={"weight_path": weight_path})

        _ckpt_dir = result_dir / "checkpoints"
        if not _ckpt_dir.exists():
            raise FileNotFoundError(f"{_ckpt_dir}: resume asked but no checkpoint dir")

        _iter = start_iter
        if _iter is None and selection is not None:
            _iter = selection(result_dir)

        if _iter is not None:
            _target = _ckpt_dir / f"checkpoint_{_iter}.pt"
            if _target.exists():
                return str(_target)
            raise FileNotFoundError(f"{_target}: no checkpoint - found {_Available(_ckpt_dir)}")

        _ckpts = _Sorted_checkpoints(_ckpt_dir)
        if _ckpts:
            return str(_ckpts[-1])
        raise FileNotFoundError(f"{_ckpt_dir}: resume asked but checkpoint dir is empty")

    if weight_path is not None:
        if Path(weight_path).exists():
            return weight_path
        raise FileNotFoundError(f"{weight_path}: no weight file")

    return None


def _Iter_of(path: Path) -> int | None:
    """`checkpoint_48.pt` / `iter_48.json` -> 48. 못 뽑으면 None."""
    _, _, _num = path.stem.rpartition("_")
    return int(_num) if _num.isdigit() else None


def _Sorted_checkpoints(ckpt_dir: Path) -> list[Path]:
    """iteration 오름차순(숫자 정렬) 체크포인트. iteration 을 못 읽는 파일 뺌."""
    _pairs = [
        (_i, _p) for _p in ckpt_dir.glob("checkpoint_*.pt")
        if (_i := _Iter_of(_p)) is not None
    ]
    return [_p for _, _p in sorted(_pairs)]


def _Available(ckpt_dir: Path) -> list[str]:
    """오류 메시지용 체크포인트 파일 이름."""
    _names = [_p.name for _p in _Sorted_checkpoints(ckpt_dir)]
    return _names if _names else ["none"]
