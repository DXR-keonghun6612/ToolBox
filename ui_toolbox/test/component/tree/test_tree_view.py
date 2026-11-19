"""tree 보기 - 깊이, 목록 순번, 목록 안 목록 한 줄, dict 목록, open 흐름.

입력 문서 : 깊이 셋의 dict, 값 목록, 목록의 목록, dict 목록, None.
"""

from __future__ import annotations

import pytest

from ui_toolbox.component.tree._view import Tree_view

_DOC = {"obj_id": 12,
        "classification": {"class_name": "bolt", "deep": {"a": {"b": 1}}},
        "scores": [0.9, 0.7],
        "K": [[1, 2, 3, 4, 5, 6], [7, 8]],
        "detections": [{"x": 1}, {"x": 2}],
        "pose": {"x": 1},
        "none": None}


def _rows(item, pad: str = "") -> list[tuple[str, str]]:
    """노드를 `(들여쓴 key, 값)` 목록으로."""
    _out = []
    for _i in range(item.childCount()):
        _c = item.child(_i)
        _out.append((pad + _c.text(0), _c.text(1)))
        _out += _rows(_c, pad + "  ")
    return _out


def test_tree_view_flow():
    # 단계 : 펼치기 - depth 2
    _t = Tree_view(depth=2, open={"detections": "dets", "pose": "pose_view"})
    _t.set_doc(_DOC)
    _r = dict(_rows(_t.invisibleRootItem()))
    assert _r["classification"] == "{2}" and _r["  class_name"] == "bolt", "expand: dict children, count"
    assert _r["  deep"] == "{1}" and "    a" not in _r, "expand: beyond depth only count"
    assert _r["  0"] in ("0.9", "[1, 2, 3, ..., 6]"), "list: index keys"
    assert _r["none"] == "", "None: empty text"

    # 단계 : 목록 안 목록 - 한 줄, 넷을 넘으면 처음 셋 ... 마지막 하나
    _k = [_v for _key, _v in _rows(_t.invisibleRootItem()) if _key.strip() in ("0", "1")]
    assert "[1, 2, 3, ..., 6]" in _k and "[7, 8]" in _k, f"list in list: {_k}"

    # 단계 : dict 목록, open 키 - 안 펼침
    _keys = [_key for _key, _ in _rows(_t.invisibleRootItem())]
    assert _r["detections"] == "[2]" and _r["pose"] == "{1}", "open key: count only"
    assert "  x" not in _keys, "open key: no children"

    # 단계 : open - 더블클릭에 영역과 값
    _got: list = []
    _t.open_requested.connect(lambda r, v: _got.append((r, v)))
    _root = _t.invisibleRootItem()
    for _i in range(_root.childCount()):
        _t.itemDoubleClicked.emit(_root.child(_i), 0)
    assert _got == [("dets", _DOC["detections"]), ("pose_view", _DOC["pose"])], f"open : {_got}"

    # 실패 갈래 : 짓기, 문서
    for _kw, _err in ((dict(depth=0), ValueError), (dict(depth="2"), TypeError), (dict(depth=1, open={"a": 3}), TypeError)):
        with pytest.raises(_err):
            Tree_view(**_kw)
    with pytest.raises(TypeError):
        _t.set_doc([1, 2])
