"""진행 막대 - 받은 수와 글자를 보이기만 하는 흐름.

전체를 알면 채워지는 막대, 모르면(0 이하) 불확정 막대.
"""

from __future__ import annotations

from ui_toolbox.component.progress._bar import Progress_bar


def test_progress_bar_flow():
    _b = Progress_bar()

    # 단계 : 전체를 앎 - 채워지는 막대, 수와 글자
    _b.report(3, 10, "detect")
    assert (_b.minimum(), _b.maximum(), _b.value()) == (0, 10, 3), "known: range, value"
    assert _b.text() == "detect : 3 / 10", "known: text"
    _b.report(3, 10)
    assert _b.text() == "3 / 10", "known: without text"

    # 단계 : 전체를 모름 - 불확정 막대, 처리한 수만
    _b.report(42, 0, "counting")
    assert (_b.minimum(), _b.maximum()) == (0, 0), "unknown: range 0"
    assert _b.format() == "counting (42)", "unknown: text"
    _b.report(0, 0)
    assert _b.format() == "", "unknown: no count, no text"
