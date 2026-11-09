# TODO - ui_toolbox

설계는 [`README.md`](README.md), 이력은 git.

## 진행 계획

### field 재설계 - 계약을 세우고 그 아래로

- [x] 자료형 판별(`list_str` · `list_pair` · `optional_float`)을 `_value.py` -> `_field.py`.
      `Field.type` 을 재는 것이라 선언 소유
- [x] `Value` 를 세 표면으로 확정하고 값 위젯이 상속.
      `Snap_slider_row.set_value` 의 신호 누출이 여기서 잡힘
- [x] `_form.py` 안 인라인 넷(`bool` · `str` · `list[str]` · `float | None`)을
      `form/widget/` 파일로. 배치가 위젯을 안 소유하게
- [x] `_int.py` · `_float.py` · `_snap.py` -> `_number.py` + 스냅 슬라이더 부품.
      스냅과 읽기 라벨은 인자. 폭은 아직 인자 - 토큰은 치수 항목에서
- [x] `form/widget/` 을 계약 import 기준으로 `value/` · `spec/` · `dialog/` 로 가름
- [x] `Path_row` 를 `Value` 로. `committed` 를 `edited` 와 `refresh` 로 가르고
      `read_only` 인자를 걷음
- [x] 치수 리터럴을 토큰으로. 없는 토큰은 `style.py` 에 더함
- [x] `_group.py` 를 `field/` 밖으로. 선언을 안 보므로 칸 주제가 아님 -> `section.py`
- [x] `_pair.py` 의 칸 선언을 소비처로 넘김. 배치가 `Rows` 를 안 지음 -
      `fields` 인자로 받고 안 주면 기본 둘
- [x] `(자료형, kind, editable) -> 위젯` 등록표를 `form/widget/` 에. `Config_form` 은 찾기만.
      `_DELEGATED` · `roi_provider` 를 같이 걷음
- [x] `Stack_view._cell` 도 같은 등록표를 봄. 라벨은 키가 아니라 빌드 인자 -
      머리줄이 이름을 이미 들면 끔

### 여러 행 - 칸 위젯과 트리

- [ ] `Table_view` 의 칸이 등록표를 봄. 지금은 Qt 기본 편집기라 같은 선언이 스택에서는
      슬라이더로, 표에서는 글자로 보임. `QStyledItemDelegate` 가 등록표를 부르게
- [ ] 중첩된 행 선언. `Rows` 는 평평해서 트리를 못 담음.
      자식이 사는 이름이 칸 이름과 겹치는 것을 막아야 함
- [ ] `Tree_view` - 그 선언을 받는 `Value`. payload 는 중첩된 `list[dict]`.
      칸 위젯은 표와 같은 등록표. `make_tree` · `set_bold` 를 여기로 흡수
- [ ] 자리 - `Table_view` 와 나란히 `form/widget/spec/`. 그러면 `form/widget/` 뿌리에
      계약을 안 보는 파일이 0

### viewport - 2D 를 못박고 3D 를 들임

- [ ] `canvas/` -> `viewport/` 리네임. 내용 변경 없음, import 방향 검사 통과
- [ ] `_canvas.py` 머리를 2D 계약으로 못박음. 빗나감이 있는 화면은 이 계약이 아님
- [ ] 3D 계약과 open3d 구현을 함께. 계약만 먼저 안 세움

### editor - 캔버스 위 층으로 들임

- [ ] LENS 의 `gui/windows/editor/` 를 들임. 계약은 도구 · 이력 · 잠금 · 조준
- [ ] 들이면서 이름을 봄 - `Target` 이 `raster` · `paint` · `bbox` 를 이름으로 듦,
      `handle/`(커서 <-> 값)이 여기 `form/` 과 겹쳐 읽힘

### 문서 패스

- [ ] `README.md` 에 `형제인가 층인가` 판별 순서
- [ ] `form/layout/` 의 README. `form/widget/` · `value/` 는 섰음
- [ ] 옛 심볼 문서의 규약 밖 표기 - em dash · `->` 아닌 화살표 · 강조 마커 · 서술형 종결.
      남은 곳 - `dialog/` · `progress/` · `viewport/`

## 합의 사항

### 폼이 받는 것은 계약 하나

`Config_form` 이 유일한 소비처. 그것이 하는 일 셋에서 표면이 나옴.

| 표면 | 무엇 |
|---|---|
| `value()` | 지금 값. payload 자료형을 안 물음 |
| `set_value()` | 값을 할당. 신호 안 냄 - 복원과 사람의 편집을 가름 |
| `edited` | 사람이 고침. payload 없음 |

- 폼이 `edited` 만 봄. 그래서 계약의 신호에 자료형이 안 듦.
  자료형 있는 `value_changed(T)` 는 직접 소비처용으로 각 위젯 소유
- 행 여럿을 미는 것(`Table_view` · `Stack_view` · `Pair_editor`)도 같은 계약.
  payload 가 `list[dict]` 일 뿐. `pairs()` 는 `value()` 로 흡수
- `changed` · `rows` · `load` 를 따로 계약으로 안 세움. 다형으로 받는 자리가 0
- 자료형이 늘 때 고치는 자리는 등록표 한 곳
- 읽기 전용은 위젯 인자가 아니라 등록표의 키 - `(자료형, kind, editable)`.
  어느 칸인지는 `Field.editable` 이 들고, 보이는 꼴은 `style.py` 의 `READOUT` 역할

### 등록표는 한 곳에서 짓는 법을 앎

`위젯이 자기를 올림` 이 아님. 값 위젯이 자기를 올리려면 `Field` 를 봐야 하는데
`form/widget/value/` 는 선언을 모르는 자리라 폴더 경계가 무너짐.

- `_registry.py` 가 그 사이를 이음 - `Field` 에서 인자를 꺼내는 것은 이 파일만
- 예외는 `Pair_editor`. 배치 층이라 위젯 층이 못 봄 -> 자기가 올림
- 검사는 등록 시점. 찾을 때 터지면 그 자리를 누가 올렸는지 못 앎
- 람다는 거부 - 이름이 없으면 오류 메시지가 `<lambda>` 로 뭉개짐.
  `python_toolbox/registry.py` 와 같은 규율. 의존은 안 엶
- `kind` 는 정확히 맞는 자리만. 없으면 기본으로 안 물러남 - 사람이 부탁한 위젯이 아닌 것이 섬
- 라벨은 키가 아니라 빌드 인자. 세로 폼은 위젯이 이름을 달고, 머리줄 있는 스택은 안 담.
  키로 세우면 같은 위젯이 자리 둘을 차지함
- 값 위젯이 `set_value(None)` 을 안 받음. 행에 칸이 없을 때 쓸 것은 `Field.default` -
  무엇을 쓸지는 선언이 정함

### 2D 와 3D 는 계약을 가름

가르는 근거는 차원이 아니라 빗나감.

| | `Canvas` (2D) | 3D 계약 |
|---|---|---|
| 받는 것 | 이미지 배열 | 점구름 · 메시 |
| 포인터가 가리키는 곳 | 늘 어느 픽셀 위 | 빈 공간일 수 있음 |
| 신호가 싣는 것 | 좌표 | 좌표 + 맞았나 |
| 보기 상태 | 배율. `0.0` = fit | 카메라 |
| 처리 주인 | 여기 - 스케일 · 스크롤 | open3d |

- 좌표 셋만으로 `안 맞음` 을 못 실음. 안 맞을 때 신호를 안 내면 조용한 fallback
- 3D 는 데이터를 받고 렌더 · 카메라 · 레이캐스트는 open3d 소유. 여기 몫은 Qt 배선
- 위젯이 장면을 드니 `맞았나` 를 냄. 소비처가 장면을 따로 안 듦
- 공통 베이스는 안 세움. `set_interactive` 하나만 겹치고 둘을 다형으로 받는 자리가 없음
- `viewport/__init__` 이 3D 이름을 안 올림 -> 라스터만 쓰는 쪽에 open3d 가 안 딸림

### 자료 구조는 선언만 지음

`form/` 은 선언을 읽어 밀 뿐. 자료 구조를 세우는 자리는 `_field.py` 하나.

| | 짓는 자리 | 읽는 자리 |
|---|---|---|
| `Field` · `Rows` | `_field.py` · 소비처 | `form/widget/` · `form/layout/` |

- 위반 - `_pair.py` 가 `Rows([Field(KEY, ...), Field(VALUE, ...)])` 를 지음. 배치가 선언을 소유
- 반대쪽 - `Collapsible` 은 선언을 하나도 안 봄. 칸 주제가 아니라 최상단 `section.py`
- 가르는 물음은 하나 - 그 파일이 `Field` 를 짓나, 읽나, 아예 모르나

### 치수는 위젯이 안 듦

`style.py` 의 치수 토큰을 코드가 `Now()` 로 읽음. 위젯 인자로도 안 받음 - 소비처마다
다른 값을 주면 테마가 다시 못 정함.

- `_bar.py` 의 `size` · `spacing`, `_number.py` 의 `width` 는 인자에서 걷힘.
  좁은 슬라이더는 `readout=True` 가 뜻까지 같이 듦
- `Field.width` 에서 오는 폭만 선언 소유. 칸마다 달라 테마가 못 정함
- `section.py` 의 `_MAX_H` 는 이 얘기 밖 - Qt 의 `QWIDGETSIZE_MAX`, `제한 없음` 파수값
- `viewport/form/widget/_raster.py` 의 `setMinimumSize(160, 120)` 은 아직. 이번 범위 밖

```bash
grep -rnE "setSpacing\([1-9]|setFixed(Width|Height|Size)\([0-9]" --include=*.py field
```

### 배치는 소비처가 코드로 조립

- 선언으로 안 옮김. 자리가 중첩이라 적으려면 HTML 같은 구조 기술이 됨. 지금 값이 없음
- 그래서 main layout 은 여기 대응 요소가 아님. 자리 이름을 아는 것은 제품 결정이라 소비처 소유
- 본문 밖에 뜨는 것(작업 창 · 팝아웃)도 같이 묶임. 창이 본문과 같은 상태를 봐야 해
  배선이 자리와 다르지만, 표준을 세우기엔 이름
- `*/form/layout/` 이 드는 것은 계약 하나를 여러 위젯으로 미는 것뿐.
  주제를 안 드는 골격(`Collapsible`)은 최상단
- `app.Run` 은 본문 위젯 하나만 받음. 나중에 선언 배치를 얹어도 안 흔들림
- 되돌아볼 조건 - 소비처가 둘 이상 생겨 같은 배선이 두 번 나올 때

### 부채

- 떼어 나오며 딸려온 도메인 어휘 하나. 걷어야 `도메인 0` 이 사실이 됨
  - `_search.py` 의 기본 제목 `class 재배정 - 대상 선택`
- 진짜 소비처 0 - 테스트만 붙어 있음. 계약은 잡히나 `사람이 보기에 쓸 만한가` 는 안 잡힘.
  아직 아무 테스트도 없는 것 - `progress/` 전부 · `Search_picker` · `Collapsible` ·
  `make_tree` · `set_bold` · `viewport/` 전부
- `Config_form` 이 폼 신호를 자기 것(`params_changed`)으로 듦. 계약의 `edited` 와 겹침.
  `Value` 로 세울지는 소비처가 폼을 값 하나로 받을 때 정함

### 드래그앤드롭이 비어 있음

- 데이터는 받을 준비가 됨 (`Rows.move_to`)
- table 표현은 Qt 내장(`InternalMove`)이라 쌈. stack 표현은 손으로 짜야 함
- 소비처가 생길 때 세움

## 논의 대상

### editor 를 범주로 들일까

LENS 의 `gui/windows/editor/` 가 도메인 0 이라 여기 올 수 있음. 계약은 도구 · 이력 · 잠금 · 조준.

- 캔버스 계약을 이미 여기가 듦. 편집기는 그 위에 서는 층
- 걸리는 것 - `Target` 이 `raster` · `paint` · `bbox` 를 이름으로 듦. 그 어휘가 일반적인가
- `handle/`(커서 <-> 값)이 여기 `form/` 과 겹쳐 읽힘. 들이면서 이름을 볼 것
