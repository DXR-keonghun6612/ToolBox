# python_toolbox

`python_toolbox`는 `Data_Schema`, 파일 I/O 디스패치, 타입 안전 registry, 프로젝트 workspace 템플릿, 작업 실행을 제공하는 범용 Python 유틸리티 패키지임.

패키지의 중심은 네 축임.

- `data_schema`: dataclass 직렬화/추출 규약
- `file`: 확장자 기반 파일 읽기/쓰기
- `registry`: 클래스 / Callable 등록 검증
- `project`: `Base_Config` + `Project_Template` + 작업(`Call_job`, `Process_job`)

---

## 개발 로그

### 1.1.0

- `project/job.py` - 작업 계약 `Job`(`on`, `start`, `stop`, `running`), 스레드 일 `Call_job`, 프로세스 일 `Process_job` · `Module_job`,
  출력 줄 규약 `Ok` · `Fail` · `Parse`, 키워드 인자 -> flag `Flags`
- `tests/` - 작업 시험
- `TODO.md` 추적 끊음 - 로컬 전용

### 1.0.1

- `file/dispatch.py` → `file/__init__.py` 병합, `Make_dict_from`·`Make_list_from` 추가
- `file/_csv.py` 구현 — DictReader/DictWriter 기반, `FILE_PROCESS` 등록
- `file` 공개 API 정리 — 내부 구현(`_base`, 핸들러 클래스) `__all__` 제외

---

## 전체 구조

```text
python_toolbox/
├── __init__.py
├── data_schema.py
├── log.py
├── registry.py
├── system.py
├── file/
│   ├── __init__.py      # Read_from, Make_dict_from, Make_list_from, Write_to, FILE_PROCESS
│   ├── _base.py
│   ├── _text.py
│   ├── _json.py
│   ├── _yaml.py
│   └── _csv.py
└── project/
    ├── __init__.py
    ├── config.py
    ├── job.py           # Job, Call_job, Process_job, Module_job, Ok, Fail, Parse, Flags
    └── template.py
```

### 공개 API

| 모듈 | 공개 항목 | 용도 |
|---|---|---|
| `python_toolbox` | `Data_Schema`, `Registry`, `Handle_exp` | 코어 유틸리티 |
| `python_toolbox.file` | `Read_from`, `Make_dict_from`, `Make_list_from`, `Write_to`, `FILE_PROCESS` | 파일 입출력 |
| `python_toolbox.project` | `Base_Config`, `Build_sub_config`, `Build_parser_from_config`, `Project_Template` | 설정/워크스페이스 |
| `python_toolbox.project` | `Job`, `Call_job`, `Process_job`, `Module_job`, `Ok`, `Fail`, `Parse`, `Flags` | 작업 실행, 출력 줄 규약 |
| `python_toolbox.system` | `String`, `Operating_System`, `Server`, `Time_Utils` | 문자열/OS/시간 유틸 |
| `python_toolbox.log` | `Logger`, `Log_Line`, `Log_Level` | 구조적 로깅 |

---

## 설계 원칙

### 1. Data_Schema 중심

구조가 있는 데이터는 우선 `Data_Schema`로 표현하고, `Serialize()` / `Extract()`를 통해 저장용 dict와 호출용 dict를 분리함.

### 2. 파일 I/O 디스패치 분리

포맷별 구현은 `file/_json.py`, `file/_yaml.py`, `file/_text.py`, `file/_csv.py`에 두고, 외부 호출은 `Read_from` / `Make_dict_from` / `Make_list_from` / `Write_to`로 통일함. 새 포맷 추가는 `FILE_PROCESS`에 핸들러를 등록하는 것으로 완결됨.

### 3. 설정과 실행 템플릿 분리

`Base_Config`는 설정 데이터 저장을 담당하고, `Project_Template`는 실행 workspace와 멱등성 `_Setup()`을 담당함.

### 4. 등록 시점 검증

`Registry`는 잘못된 클래스 상속이나 Callable 시그니처 불일치를 등록 시점에 차단함.

### 5. 작업은 화면을 모름

`Job`은 일을 돌리고 콜백(`start`, `progress`, `line`, `finish`)만 냄. 콜백은 작업의 스레드에서 불리고, GUI 스레드로 넘기는 것은 부르는 쪽(ui_toolbox `Job_popup`)이 맡음. 출력 줄 규약(`ok <key>` / `fail <key> <reason>`)은 UI 를 모르는 작업 프로그램과 `Process_job`이 같은 함수로 씀.
