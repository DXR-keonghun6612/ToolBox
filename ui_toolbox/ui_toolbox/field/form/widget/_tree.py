"""트리 위젯 기본값 - 컬럼 · 헤더 · resize · 교차 배경을 한 자리에.

계약이 안 섬. 앉힐 기본값뿐이라 함수 둘.
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem


def make_tree(
    *,
    headers: Sequence[str] | None = None,
    columns: int | None = None,
    hidden: bool = False,
    resize: Sequence[QHeaderView.ResizeMode | None] | None = None,
    alternating: bool = False,
) -> QTreeWidget:
    """공통 설정을 적용한 ``QTreeWidget`` 을 만든다.

    Args:
        headers: 헤더 라벨. 주면 컬럼 수도 이 길이로 맞춘다.
        columns: 헤더를 숨길 때(또는 라벨 없이) 컬럼 수만 지정.
        hidden: True 면 헤더를 숨김. `headers` 보다 우선.
        resize: 컬럼별 ``QHeaderView.ResizeMode`` (``None`` 항목은 건너뜀).
        alternating: True면 교차 행 배경.

    Returns:
        설정이 적용된 ``QTreeWidget``.
    """
    _tree = QTreeWidget()
    _n = len(headers) if headers else (columns or 0)
    if _n:
        _tree.setColumnCount(_n)
    if hidden:
        _tree.setHeaderHidden(True)
    elif headers:
        _tree.setHeaderLabels(list(headers))
    if resize:
        _hdr = _tree.header()
        for _i, _mode in enumerate(resize):
            if _mode is not None:
                _hdr.setSectionResizeMode(_i, _mode)
    if alternating:
        _tree.setAlternatingRowColors(True)
    return _tree


def set_bold(item: QTreeWidgetItem, col: int = 0) -> None:
    """트리 아이템의 특정 컬럼 글꼴을 굵게 만든다."""
    _f = item.font(col)
    _f.setBold(True)
    item.setFont(col, _f)
