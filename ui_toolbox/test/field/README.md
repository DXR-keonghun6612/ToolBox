# test/field - 칸 주제

## 구조

### test_field.py

| 축 | 확인하는 것 |
|---|---|
| 자료형 판별 | `list[str]` · `list[tuple[str, str]]` · `float \| None`. Optional 겹침도 같은 답 |
| 정렬 자리 | 빈 값이 뒤. 수는 수로, 글자는 수 `0` 자리 |
| 행 | 같은 값이면 안 바뀜. 사본으로 냄, 범위 밖 이동은 제자리 |
| 보이는 글자 | `display` 를 거침, 빈 값은 안 넘김. 필터링은 선언된 모든 칸의 그 글자 |
| 와일드카드 | `*` 는 0 자 이상, `?` 는 한 자. 그 밖 정규식 글자는 글자 그대로 |

### test_value.py

| 축 | 확인하는 것 |
|---|---|
| 상속 | 값 위젯 여덟이 `Value` |
| 복원 | `set_value` 가 신호 안 냄. 값은 그대로, 범위 밖은 잘림 |
| 편집 | 사람이 고치면 `edited` 와 `value_changed` 를 한 번씩 |
| 스냅 | 드래그에만 걸림. `set_value` 에는 안 걸리고, 읽기 라벨은 두 길 다 따라감 |
| 경로 | `refresh` 는 값 사건이 아님. 초점만 옮긴 것도 편집이 아님 |

### test_token.py

| 축 | 확인하는 것 |
|---|---|
| 읽는 길 | 간격 · 버튼 크기 · 좁은 폭이 `Use()` 로 갈아끼운 토큰을 따라감 |
| 선언 소유 | `Field.width` 는 테마가 안 건드림 |

### test_registry.py

| 축 | 확인하는 것 |
|---|---|
| 올릴 때 막음 | 람다 · 인자 수 · 이미 찬 자리 |
| 자리 | 아홉 키가 각자 자기 위젯을 냄. 빈 자리는 `None` |
| 읽기 전용 글자 | 선언의 `display` 를 따르고 값은 그대로 |

### test_form.py

| 축 | 확인하는 것 |
|---|---|
| 자료형 덮기 | 선언한 일곱 자료형이 모두 위젯을 얻음 |
| 실패 | 자리 없는 자료형도, 모르는 `kind` 도 `TypeError`. 조용히 안 버림 |
| 키 | `kind` 가 위젯을 가름. `editable=False` 는 읽기 전용이고 자료형이 안 상함 |
| 복원 | `load` 가 `params_changed` 안 냄. 모르는 키는 무시 |
| 편집 | 사람이 고치면 `params_changed` |

### test_stack.py

| 축 | 확인하는 것 |
|---|---|
| 계약 | 행 여럿을 미는 셋이 `Value`. payload 가 `list[dict]` 로 왕복하고 복원은 조용함 |
| 칸 위젯 | 폼과 같은 등록표에서 옴. 라벨은 안 달고, 자리 없는 자료형은 `TypeError` |
| 빈 칸 | 그 행에 칸이 없으면 `Field.default` |
| 쌍 | 중복 key 를 살리고 빈 key 는 뺌. 칸 선언은 소비처가 줌 |

### test_table.py

| 축 | 확인하는 것 |
|---|---|
| 보이는 글자 | 화면은 `display`, 편집은 값. 필터링은 글자로, 정렬은 값으로 |
| 정렬 사슬 | 칸 하나가 `없음 -> 오름 -> 내림 -> 없음`. 일반은 다른 칸을 풀고 `keep` 은 뒤에 붙임. 머리글 번호는 사슬일 때만. `reset` 이 필터링과 정렬을 다 풀음 |
| 붙이기 | 리셋 없이 한 번에 끼움, 신호 안 냄. 고른 것이 그대로, 필터링에 안 걸리면 안 보임 |
| 정렬 중 붙이기 | 오름 · 내림 · 사슬 모두 다시 정렬한 자리와 같음. 같은 값은 원본 순서 |
| 칸 폭 | 합이 표 폭. `width` 는 비율, 없는 칸은 선언된 폭의 평균 |
| 조작 줄 | 뷰어면 버튼 없음. 선택 삭제는 원본 자리를 신호로 내고 행은 그대로. 목록 초기화는 물어서 `Yes` 일 때만 신호 |

## 기반

Qt 앱은 세션에 하나, 화면 없이. 부르는 쪽이 환경변수를 안 걺.

```python
# ../conftest.py
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # QApplication 보다 먼저

@pytest.fixture(scope="session", autouse=True)
def _qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])
```

칸 선언 하나가 폼도 표도 세움. 세로 한 벌이면 폼, 행 여럿이면 표 · 스택.

```python
FIELDS = [
    Field("이름", str, "무제", tip="파일명에 씀"),
    Field("비율", float, 0.5, min=0.0, max=1.0, step=0.1),
    Field("칸수", int, 3, min=1, max=10),
    Field("켬", bool, True),
    Field("경로", str, kind="path"),              # kind 가 위젯을 가름
    Field("태그", list[str], ["a", "b"]),          # 쉼표로 가른 한 줄
    Field("한계", float | None),                   # 체크박스 + 슬라이더
    Field("지문", str, "고정", editable=False),     # 읽기 전용
]

_form = Config_form(FIELDS)
_form.params_changed.connect(on_edit)   # 사람이 고칠 때만
_form.load(saved)                       # 복원 - 신호 안 냄
saved = _form.get()                     # {이름: 값}
```

값이 여럿이면 같은 선언에 `Rows` 를 얹음. 셋 다 `Value` 라 소비처가 하나로 받음.

```python
def _rows() -> Rows:
    """표현마다 하나씩. 위젯이 제자리에서 고치므로 나눠 쓰면 화면이 어긋남."""
    return Rows(FIELDS[:4], [{"이름": "a", "칸수": 3}, {"이름": "b"}])

_table = Table_view(_rows(), movable=True)    # 칸 고정. 정렬 · 필터링. 뷰어

# 행을 늘리고 줄이는 목록. 버튼은 신호만 - 원본을 고치고 set_value 로 되비춤
_list = Table_view(_rows(), editable=True)
_list.add_requested.connect(on_add)
_list.remove_requested.connect(on_remove)     # 고른 항목의 원본 자리
_list.clear_requested.connect(on_clear)       # 위젯이 물은 뒤

# 행이 계속 붙는 목록. 글자는 보일 때만 지음, 붙일 때 리셋 없음
_log = Table_view(Rows([Field("시각", float, editable=False, display=_stamp)]))
_log.extend(new_rows)                          # 신호 안 냄 - set_value 와 같은 쪽
_stack = Stack_view(_rows(), movable=True)    # 칸이 상황따라 숨음
_pairs = Pair_editor(kind="path")             # key/value. 중복 key 허용

for _w in (_table, _stack, _pairs):
    _w.edited.connect(on_edit)
_stack.set_value([{"이름": "z"}])              # 복원 - 신호 안 냄
```

자료형이 늘면 등록표 한 줄. 폼도 스택도 같은 표를 봄.

```python
@Register("duration", kind="", editable=True)
def _duration(spec: Field, label: str) -> QWidget:
    """인자는 `(칸 선언, 라벨)` 둘. 람다는 안 받음."""
    return Duration_row(label, spec.default, tooltip=spec.tip)
```

값 위젯을 직접 쓸 때는 자료형 있는 신호로 받음.

```python
_row = Int_slider_row("밝기", -100, 100, 0, snaps=[0], readout=True)
_row.value_changed.connect(lambda v: canvas.set_brightness(v))
_row.set_value(30)                 # 스냅 안 걸림, 신호 안 남
```

색 · 치수를 바꾸려면 위젯을 짓기 전에 토큰을 갊.

```python
Use(Style(gap=6, button=26, accent="#c76b2a"))
```

```bash
python -m pytest test -q
```
