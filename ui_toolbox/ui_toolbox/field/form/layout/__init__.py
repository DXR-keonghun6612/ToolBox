"""여러 위젯 배치 - 한 행을 세로로(폼), 여러 행을 세로로(스택).

`_pair` 를 여기서 부르는 것이 등록을 세움 - 안 부르면 `Config_form` 이 쌍 목록 칸에서
자리 없음으로 터짐. 조용히 안 넘어가므로 순서가 틀리면 드러남.
"""

from ._form import Config_form
from ._pair import Pair_editor
from ._stack import Stack_view

__all__ = ["Config_form", "Pair_editor", "Stack_view"]
