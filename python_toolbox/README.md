# python_toolbox

`python_toolbox`는 `Data_Schema`, 파일 I/O 디스패치, 타입 안전 registry, 실행 결과 자리, 작업 실행을 제공하는 범용 Python 유틸리티 패키지임.

- `schema/`: dataclass 꼴과 직렬화 - `Data_Schema`, 그 위의 설정(`Base_Config`), 로그(`Log_Line`)
- `run/`: 한 번의 실행 - 작업(`Call_job`, `Process_job`), 결과 자리(`Workspace`)
- `file/`: 확장자 기반 파일 읽기/쓰기
- `registry`: 클래스 / Callable 등록 검증
- `system`: 문자열, OS, 시간 유틸

---

## 개발 로그

### 2.0.0

- `project/` 해체 - `data_schema`, `log`, `project/config` 는 `schema/`, `project/job`, `project/template` 은 `run/`. import 경로가 바뀜
- `Project_Template` -> `run/workspace.py` 의 `Workspace`
- `schema/`, `run/` 에 `__init__.py` 없음 - 모듈까지 적어 import
- `project/COOKBOOK.md` 지움

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
├── registry.py
├── system.py
├── schema/
│   ├── data_schema.py   # Data_Schema
│   ├── config.py        # Base_Config, Build_config, Build_config_from_file, Build_parser_from_config
│   └── log.py           # Logger, Log_Line, Log_Level
├── run/
│   ├── job.py           # Job, Call_job, Process_job, Module_job, Ok, Fail, Parse, Flags
│   └── workspace.py     # Workspace, RESULT_ROOT
└── file/
    ├── __init__.py      # Read_from, Make_dict_from, Make_list_from, Write_to, FILE_PROCESS
    ├── _base.py
    ├── _text.py
    ├── _json.py
    ├── _yaml.py
    ├── _csv.py
    └── group.py
```

### 공개 API

| 모듈 | 공개 항목 | 용도 |
|---|---|---|
| `python_toolbox.schema.data_schema` | `Data_Schema` | dataclass 직렬화/추출 |
| `python_toolbox.schema.config` | `Base_Config`, `Build_config`, `Build_config_from_file`, `Build_parser_from_config` | 설정 |
| `python_toolbox.schema.log` | `Logger`, `Log_Line`, `Log_Level` | 구조적 로깅 |
| `python_toolbox.run.job` | `Job`, `Call_job`, `Process_job`, `Module_job`, `Ok`, `Fail`, `Parse`, `Flags` | 작업 실행, 출력 줄 규약 |
| `python_toolbox.run.workspace` | `Workspace`, `RESULT_ROOT` | 실행 결과 자리 |
| `python_toolbox.file` | `Read_from`, `Make_dict_from`, `Make_list_from`, `Write_to`, `FILE_PROCESS` | 파일 입출력 |
| `python_toolbox.registry` | `Registry` | 등록 검증 |
| `python_toolbox.system` | `String`, `Operating_System`, `Server`, `Time_Utils` | 문자열/OS/시간 유틸 |

---

## 설계 원칙

### 1. Data_Schema 중심

구조가 있는 데이터는 우선 `Data_Schema`로 표현하고, `Serialize()` / `Extract()`를 통해 저장용 dict와 호출용 dict를 분리함.

### 2. 파일 I/O 디스패치 분리

포맷별 구현은 `file/_json.py`, `file/_yaml.py`, `file/_text.py`, `file/_csv.py`에 두고, 외부 호출은 `Read_from` / `Make_dict_from` / `Make_list_from` / `Write_to`로 통일함. 새 포맷 추가는 `FILE_PROCESS`에 핸들러를 등록하는 것으로 완결됨.

### 3. 설정과 결과 자리 분리

`Base_Config`(`schema/`)는 설정 데이터 저장을 담당하고, `Workspace`(`run/`)는 실행 결과 자리와 멱등성 `_Setup()`을 담당함.

### 4. 등록 시점 검증

`Registry`는 잘못된 클래스 상속이나 Callable 시그니처 불일치를 등록 시점에 차단함.

### 5. 작업은 화면을 모름

`Job`은 일을 돌리고 콜백(`start`, `progress`, `line`, `finish`)만 냄. 콜백은 작업의 스레드에서 불리고, GUI 스레드로 넘기는 것은 부르는 쪽(ui_toolbox `Job_popup`)이 맡음. 출력 줄 규약(`ok <key>` / `fail <key> <reason>`)은 UI 를 모르는 작업 프로그램과 `Process_job`이 같은 함수로 씀.

### 6. 폴더는 묶는 축이 안에 있을 때만

`schema/` 는 `Data_Schema` 와 그 위의 꼴(설정, 로그), `run/` 은 한 번의 실행(작업, 결과 자리), `file/` 은 디스패치 하나 뒤의 포맷 처리기. 축이 없는 것(`registry`, `system`)은 바로 아래 낱개. `schema/`, `run/` 은 다시 내보낼 것이 없어 `__init__.py` 없음 - 모듈까지 적어 import.
