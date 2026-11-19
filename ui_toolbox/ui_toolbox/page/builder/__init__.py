"""builder - config node 를 읽어 위젯을 짓고 놓음. 찾기는 `_find`, 배치는 `_place`, 묶음은 `_names`, style 은 `_sheet`.

page 의 popup 클래스(`Popup`, `Job_popup`)를 앎 - link 에 지음. page 구성(`Main`)이 `Fill` 을 씀.

node
- 칸은 일곱 - `title`, `class`, `args`, `items`, `link`, `action`, `style`. 모르는 칸은 실패
- node 마다 `style` -> `link` -> `action` -> `items` 차례 - 적은 차례와 상관없음
- `args` 는 `class` 의 생성자 인자 그대로
- `title` 은 부모의 배치가 읽음. 창(root, popup)은 창 제목. 없으면 key

배치
- `class` 가 배치면 container. `items`, `link`, `action` 은 container 만
- root 의 `class` 는 배치, root `items` 바로 아래는 container 만. popup 은 component 를 바로 둬도 됨
- `items` 는 맵 또는 yaml 경로 - 경로는 그 node 를 적은 파일의 폴더 기준, 파일에는 `items` 맵만

key
- `objectName`, style selector, 묶음의 이름. `_` 로 시작 안 함
- container 마다 묶음 셋 - `.items`, `.link`, `.action`. 따로라 같은 key 여도 됨, Qt 이름과 안 부딪힘

영역
- `regions()` 가 있는 component 는 낼 영역 이름을 알림 - 보이는 link key 또는 그 page(root, popup)의 items key 여야 함.
  아니면 실패. link 는 적은 node 아래에서만 보임

link
- 늘 popup - `class` 가 배치면 `Popup` 을 지어 그 `body` 에 걺(`args` 는 `Popup` 의 것), `QDialog` 면 그대로
- Qt 부모는 link 를 적은 node - 창 꼴은 지킴, 부모 배치에 안 듦

action
- 첫 단은 붙는 자리 - `menu`(메뉴 막대), `context`(우클릭 메뉴)
- 그 아래는 `items` 가 있으면 하위 메뉴, 없으면 action(`title`, `args`). 한 node 의 action key 는 자리, 하위 메뉴와 상관없이 하나.
  두 자리에 붙이려면 두 번 적음

style
- 위에서 받은 것 위에 node 의 것을 덮어 아래로 넘김. 시트는 창과 제 `style` 이 있는 node 에만
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QLayout, QMenu, QWidget
from python_toolbox.file import Make_dict_from

from .._popup import Popup
from ._find import Find, Find_at, Is_host, Is_layout
from ._names import Names
from ._place import Arrange, Make, Place
from ._sheet import Cascade, Sheet

__all__ = ["FIELDS", "Fill", "Find", "Names", "Sheet"]

#: 실패 글자의 경로 맨 앞 - root node.
ROOT = "root"

#: node 칸.
FIELDS = ("title", "class", "args", "items", "link", "action", "style")

#: action 의 첫 단 - 붙는 자리.
PLACES = ("menu", "context")

#: action node 칸 - `items` 가 있으면 하위 메뉴.
_ACTION_FIELDS = ("title", "args", "items")


# ── 검사 ──────────────────────────────────────────────────────────────────────
def _key(key: Any, where: str) -> None:
    """key 는 속성 이름이 되는 글자 - `_` 로 시작 안 함.

    Raises:
        ValueError: 아닐 때.
    """
    if not isinstance(key, str) or not key.isidentifier() or key.startswith("_"):
        raise ValueError(f"{where}: key must be an identifier not starting with '_' - got {key!r}")


def _node(node: Any, where: str) -> dict:
    """node 칸 검사.

    Raises:
        TypeError: node 가 맵이 아닐 때, 칸의 자료형이 어긋날 때.
        ValueError: 모르는 칸일 때.
    """
    if not isinstance(node, dict):
        raise TypeError(f"{where}: node must be a map - got {type(node).__name__}")
    _unknown = [_k for _k in node if _k not in FIELDS]
    if _unknown:
        raise ValueError(f"{where}: unknown fields {_unknown} - known {list(FIELDS)}")
    for _f, _want in (("title", str), ("class", str), ("args", dict), ("link", dict), ("action", dict),
                      ("style", dict), ("items", (dict, str))):
        if _f in node and not isinstance(node[_f], _want):
            raise TypeError(f"{where}.{_f}: wrong type - got {type(node[_f]).__name__}")
    return node


def _attach(owner: Any, key: str, value: Any, where: str) -> None:
    """`owner.key = value`.

    Raises:
        KeyError: 이미 있는 이름(Qt 메서드 등)과 겹칠 때.
    """
    if hasattr(owner, key):
        raise KeyError(f"{where}: {key!r} clashes with a {type(owner).__name__} name")
    setattr(owner, key, value)


# ── 짓기 ──────────────────────────────────────────────────────────────────────
class _Build:
    """한 번 짓는 동안의 상태 - 시트를 걸 자리, 모든 node key, 영역 이름 검사."""

    def __init__(self) -> None:
        self.sheets: list[tuple[QWidget, dict]] = []
        self.keys: set[str] = set()
        self.checks: list[tuple[str, set[str], frozenset[str], set[str]]] = []

    def fill(self, widget: QWidget, place: Place, node: dict, base: Path, style: dict, where: str,
             window: bool, title: str | None, links: frozenset[str], page_keys: set[str]) -> None:
        """container 하나를 채움 - `style` -> `link` -> `action` -> `items`.

        Args:
            links: 위 node 들의 link key - 이 node 아래에서 영역 이름으로 보임.
            page_keys: 이 page(root 또는 popup)의 items key - 다 지은 뒤 영역 이름 검사에 씀.
        """
        _style = Cascade(style, node["style"], where) if "style" in node else style
        if window or "style" in node:
            self.sheets.append((widget, _style))
        _title = node.get("title", title)
        if window and _title:
            widget.setWindowTitle(_title)
        for _attr in ("items", "link", "action"):
            _attach(widget, _attr, Names(), where)

        _links = links | frozenset(node.get("link", {}))
        for _key_, _sub in node.get("link", {}).items():
            self.link(widget, _key_, _sub, base, _style, f"{where}.link", _links)
        for _at, _tree in node.get("action", {}).items():
            self.action(widget, place, _at, _tree, f"{where}.action")
        _items, _base = self.items(node.get("items", {}), base, where)
        for _key_, _sub in _items.items():
            self.item(widget, place, _key_, _sub, _base, _style, f"{where}.items", _links, page_keys)

    def items(self, value: dict | str, base: Path, where: str) -> tuple[dict, Path]:
        """`items` - 맵, 또는 맵을 담은 파일 경로(그 node 를 적은 파일의 폴더 기준).

        Raises:
            ValueError: 파일을 못 읽을 때, 담긴 것이 맵이 아닐 때.
        """
        if isinstance(value, dict):
            return value, base
        _path = base / value
        _ok, _data = Make_dict_from(_path)
        if not _ok or not isinstance(_data, dict):
            raise ValueError(f"{where}.items: cannot read a map from {_path}")
        return _data, _path.parent

    def item(self, owner: QWidget, place: Place, key: str, sub: Any, base: Path, style: dict,
             where: str, links: frozenset[str], page_keys: set[str]) -> None:
        """배치에 드는 node 하나."""
        _key(key, where)
        _where = f"{where}.{key}"
        _sub = _node(sub, _where)
        if "class" not in _sub:
            raise ValueError(f"{_where}: no class")
        _cls = Find_at(_sub["class"], _where)
        _args = _sub.get("args", {})
        if issubclass(_cls, QLayout):
            _child = QWidget()
            _place: Place | None = Arrange(_child, _cls, _args, _where)
        elif Is_host(_cls):
            _child = Make(_cls, _args, _where)
            _place = Place(None, _child)
        elif issubclass(_cls, QWidget):
            _child = Make(_cls, _args, _where)
            _place = None
        else:
            raise TypeError(f"{_where}: items class must be a widget or layout - got {_cls.__name__}")
        owner.items.put(key, _child, _where)
        _child.setObjectName(key)
        place.add(_child, _sub.get("title", key))
        self.keys.add(key)
        page_keys.add(key)
        if callable(getattr(_child, "regions", None)):
            self.checks.append((_where, set(_child.regions()), links, page_keys))
        if _place is not None:
            self.fill(_child, _place, _sub, base, style, _where, window=False, title=None,
                      links=links, page_keys=page_keys)
            return
        _only = [_f for _f in ("items", "link", "action") if _f in _sub]
        if _only:
            raise ValueError(f"{_where}: {_only} need a layout class - got {_sub['class']!r}")
        if "style" in _sub:
            self.sheets.append((_child, Cascade(style, _sub["style"], _where)))

    def link(self, owner: QWidget, key: str, sub: Any, base: Path, style: dict, where: str,
             links: frozenset[str]) -> None:
        """배치에 안 드는 node 하나 - 늘 popup."""
        _key(key, where)
        _where = f"{where}.{key}"
        _sub = _node(sub, _where)
        if "class" not in _sub:
            raise ValueError(f"{_where}: no class - expected a layout or popup class")
        _cls = Find_at(_sub["class"], _where)
        _args = _sub.get("args", {})
        if Is_layout(_cls):
            _pop = Make(Popup, _args, _where)
            _place: Place | None = Arrange(_pop.body, _cls, {}, _where)
        elif issubclass(_cls, QDialog):
            _pop = Make(_cls, _args, _where)
            _place = None
        else:
            raise TypeError(f"{_where}: link class must be a layout or popup class - got {_cls.__name__}")
        _pop.setParent(owner, _pop.windowFlags())          # 창 꼴을 지킴 - 부모 배치에 안 듦
        _pop.setObjectName(key)
        owner.link.put(key, _pop, _where)
        self.keys.add(key)
        if _place is not None:
            self.fill(_pop, _place, _sub, base, style, _where, window=True, title=key,
                      links=links, page_keys=set())
            return
        _only = [_f for _f in ("items", "link", "action") if _f in _sub]
        if _only:
            raise ValueError(f"{_where}: {_only} need a layout class - got {_sub['class']!r}")
        _style = Cascade(style, _sub["style"], _where) if "style" in _sub else style
        self.sheets.append((_pop, _style))
        _pop.setWindowTitle(_sub.get("title", key))

    def action(self, owner: QWidget, place: Place, at: str, tree: Any, where: str) -> None:
        """action 첫 단 하나 - 붙는 자리.

        Raises:
            ValueError: 모르는 자리일 때.
        """
        if at == "menu":
            _host = place.menu_bar(where.rsplit(".", 1)[0])
        elif at == "context":
            owner.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
            _host = owner
        else:
            raise ValueError(f"{where}: unknown place {at!r} - known {list(PLACES)}")
        self.menu(owner, _host, tree, f"{where}.{at}")

    def menu(self, owner: QWidget, host: QWidget, tree: Any, where: str) -> None:
        """메뉴 하나를 채움 - `items` 가 있으면 하위 메뉴, 없으면 action."""
        if not isinstance(tree, dict):
            raise TypeError(f"{where}: expected a map - got {type(tree).__name__}")
        for _k, _sub in tree.items():
            _key(_k, where)
            _where = f"{where}.{_k}"
            if not isinstance(_sub, dict):
                raise TypeError(f"{_where}: expected a map - got {type(_sub).__name__}")
            _unknown = [_f for _f in _sub if _f not in _ACTION_FIELDS]
            if _unknown:
                raise ValueError(f"{_where}: unknown fields {_unknown} - known {list(_ACTION_FIELDS)}")
            _title = _sub.get("title", _k)
            if "items" in _sub:
                if "args" in _sub:
                    raise ValueError(f"{_where}: a submenu takes no args")
                _menu = QMenu(_title, owner)
                _menu.setObjectName(_k)
                host.addAction(_menu.menuAction())
                self.menu(owner, _menu, _sub["items"], f"{_where}.items")
                continue
            _args = _sub.get("args", {})
            if not isinstance(_args, dict):
                raise TypeError(f"{_where}.args: expected a map - got {type(_args).__name__}")
            try:
                _act = QAction(_title, owner, **_args)
            except (TypeError, AttributeError) as _e:
                raise TypeError(f"{_where}: cannot build QAction({_args}) - {_e}") from _e
            owner.action.put(_k, _act, f"{_where} (one per node across places and submenus)")
            _act.setObjectName(_k)
            host.addAction(_act)

    def apply(self) -> None:
        """다 지은 뒤 - 영역 이름을 검사하고 시트를 걺. 모든 key 를 안 뒤라 둘 다 여기서.

        Raises:
            KeyError: component 가 낼 영역 이름이 보이는 link key 도, 그 page 의 items key 도 아닐 때.
        """
        for _where, _regions, _links, _page_keys in self.checks:
            _lost = sorted(_r for _r in _regions if _r not in _links and _r not in _page_keys)
            if _lost:
                raise KeyError(f"{_where}: unknown regions {_lost} - visible links {sorted(_links)}, "
                               f"page items {sorted(_page_keys)}")
        for _w, _style in self.sheets:
            _w.setStyleSheet(Sheet(_style, self.keys))


def Fill(widget: QWidget, config: dict, base: str | Path = ".", style: dict | None = None) -> None:
    """root node 를 이미 지은 위젯(main)에 채움.

    Args:
        widget: root 위젯 - 소비처 page.
        config: root node.
        base: `items` 파일 경로의 기준 폴더.
        style: 위에서 받는 style - 공통 style. 비면 없음.

    Raises:
        TypeError: 칸의 자료형이 어긋날 때, 생성자가 인자를 안 받을 때.
        ValueError: 모르는 칸, 모르는 자리, 잘못된 key, 파일을 못 읽을 때, root items 에 container 가 아닌 것.
        KeyError: 없는 이름, 겹치는 key, 없는 영역 이름일 때.
    """
    _root = _node(config, ROOT)
    if "class" not in _root:
        raise ValueError(f"{ROOT}: no class - expected the root layout")
    _cls = Find_at(_root["class"], ROOT)
    if not Is_layout(_cls):
        raise TypeError(f"{ROOT}: class must be a layout - got {_cls.__name__}")
    for _k, _sub in (_root["items"] if isinstance(_root.get("items"), dict) else {}).items():
        _where = f"{ROOT}.items.{_k}"
        if isinstance(_sub, dict) and "class" in _sub and not Is_layout(Find_at(_sub["class"], _where)):
            raise ValueError(f"{_where}: root items must be containers - got {_sub['class']!r}")
    _job = _Build()
    _place = Arrange(widget, _cls, _root.get("args", {}), ROOT)
    _job.fill(widget, _place, _root, Path(base), dict(style or {}), ROOT, window=True, title=None,
              links=frozenset(), page_keys=set())
    _job.apply()
