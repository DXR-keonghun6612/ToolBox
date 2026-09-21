from __future__ import annotations
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from python_toolbox.file import Read_from

SELECT_RULE = Callable[[Mapping[int, float]], int]    #: `{iter: 점수}` -> iter


def Max_of(scores: Mapping[int, float]) -> int:
    """점수 최대 iteration. 동률이면 나중 것."""
    return max(sorted(scores, reverse=True), key=lambda _k: scores[_k])


def Min_of(scores: Mapping[int, float]) -> int:
    """점수 최소 iteration. 동률이면 나중 것."""
    return min(sorted(scores, reverse=True), key=lambda _k: scores[_k])


@dataclass(frozen=True)
class Iter_Selection:
    """복원할 iteration 선택. 러너가 `ClassVar` 로 선언.

    Attributes:
        rule: `SELECT_RULE`. 예 `Min_of`, `Max_of`.
        mode: 로그 mode (`train` / `val` 등).
        metric: 지표 이름 (`accuracy` / `loss` 등).
    """

    rule: SELECT_RULE
    mode: str
    metric: str

    def __call__(self, workspace: Path) -> int:
        """학습 로그에서 iteration 선택.

        Raises:
            FileNotFoundError: 그 mode 의 로그 디렉터리 없음.
            ValueError: 그 지표를 가진 iteration 없음.
        """
        _scores = Read_metric_log(workspace, self.mode, self.metric)
        _pick = self.rule(_scores)
        print(f"[INFO] iter {_pick} 선택 ({self.rule.__name__} of "
              f"{self.mode}/{self.metric}={_scores[_pick]:.6f}, 후보 {len(_scores)}개)")
        return _pick


def Read_metric_log(workspace: Path, mode: str, metric: str) -> dict[int, float]:
    """`avg/<mode>/<acc_name>/iter_<i>.json` (`log_iter` 출력) -> `{iter: 값}`.

    Raises:
        FileNotFoundError: 그 mode 의 로그 디렉터리 없음.
        ValueError: 지표 없음, 또는 여러 accumulator 가 같은 이름을 냄.
    """
    _dir = workspace / "avg" / mode
    if not _dir.exists():
        raise FileNotFoundError(
            f"학습 로그가 없다: {_dir}. 학습을 돌렸는지, mode 이름('{mode}')이 맞는지 "
            f"확인할 것."
        )

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
        raise ValueError(
            f"'{metric}' 를 내는 accumulator 가 둘 이상이다({sorted(_sources)}). "
            f"어느 것을 볼지 모호하다."
        )
    if not _scores:
        _seen = sorted({_p.parent.name for _p in _dir.glob("*/iter_*.json")})
        raise ValueError(
            f"로그에 '{metric}' 지표가 없다. {_dir} 의 accumulator: "
            f"{_seen if _seen else '없음'}"
        )
    return _scores


def Resolve_weight_path(
    resume_path: str | None,
    weight_path: str | None,
    workspace: Path,
    start_iter: int | None,
    selection: Iter_Selection | None = None,
) -> str | None:
    """가중치 파일 경로 해석. `resume_path` 우선, 다음 `weight_path`, 둘 다 없으면 None.
    resume 의 iteration 은 `start_iter` -> `selection` -> 마지막 체크포인트.

    Args:
        resume_path: run 디렉터리명. `workspace/checkpoints` 에서 찾음.
        weight_path: 가중치 파일 경로.
        workspace: run 디렉터리.
        start_iter: 지목할 iteration.
        selection: iteration 선택 방법.

    Raises:
        FileNotFoundError: 가중치를 요구했으나 못 찾음.
    """
    if resume_path is not None:
        if weight_path is not None:
            print("[WARN] --resume과 --weight 동시 지정됨. --weight는 무시함.")

        _ckpt_dir = workspace / "checkpoints"
        if not _ckpt_dir.exists():
            raise FileNotFoundError(
                f"resume을 요구했으나 checkpoint 디렉터리가 없음: {_ckpt_dir}. "
                f"--resume_path 에는 상위 경로 없이 run 디렉터리명만 준다."
            )

        _iter = start_iter
        if _iter is None and selection is not None:
            _iter = selection(workspace)

        if _iter is not None:
            _target = _ckpt_dir / f"checkpoint_{_iter}.pt"
            if _target.exists():
                return str(_target)
            raise FileNotFoundError(
                f"checkpoint 파일 없음: {_target}. "
                f"{_ckpt_dir} 에 있는 것: {_Available(_ckpt_dir)}"
            )

        _ckpts = _Sorted_checkpoints(_ckpt_dir)
        if _ckpts:
            return str(_ckpts[-1])
        raise FileNotFoundError(
            f"resume을 요구했으나 checkpoint 디렉터리가 비어 있음: {_ckpt_dir}"
        )

    if weight_path is not None:
        if Path(weight_path).exists():
            return weight_path
        raise FileNotFoundError(f"weight 파일 없음: {weight_path}")

    return None


def _Iter_of(path: Path) -> int | None:
    """`checkpoint_48.pt` / `iter_48.json` -> 48. 못 뽑으면 None."""
    _, _, _num = path.stem.rpartition("_")
    return int(_num) if _num.isdigit() else None


def _Sorted_checkpoints(ckpt_dir: Path) -> list[Path]:
    """iter 오름차순 (숫자 정렬) 체크포인트. iter 를 못 읽는 파일 제외."""
    _pairs = [
        (_i, _p) for _p in ckpt_dir.glob("checkpoint_*.pt")
        if (_i := _Iter_of(_p)) is not None
    ]
    return [_p for _, _p in sorted(_pairs)]


def _Available(ckpt_dir: Path) -> list[str]:
    """오류 메시지용 체크포인트 파일명 목록."""
    _names = [_p.name for _p in _Sorted_checkpoints(ckpt_dir)]
    return _names if _names else ["없음"]
