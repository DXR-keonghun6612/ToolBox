# HUB

개인 연구 및 개발 효율화를 위한 기술 스택 모노레포입니다.
각 서브디렉토리는 특정 목적을 위한 독립적인 도구 및 코드 모음입니다.

## Contents

| 디렉토리 | 설명 |
| --- | --- |
| [python_toolbox](./python_toolbox) | 범용 Python 유틸리티 (Data_Schema, 파일 I/O, Registry, Config) |
| [bash_toolbox](./bash_toolbox) | OS 비종속 범용 쉘 스크립트 라이브러리 |
| [torch_toolbox](./torch_toolbox) | PyTorch 기반 딥러닝 파이프라인 프레임워크 |
| [spatial_toolbox](./spatial_toolbox) | 3D scene graph 관리·렌더링·시뮬레이션 패키지 |
| [vision_toolbox](./vision_toolbox) | 2D-3D 비전 연산 라이브러리 |
| [ui_toolbox](./ui_toolbox) | PySide6 기반 도메인 비종속 Qt 부품 - component, config 로 짓는 page |

## Install

python 패키지 설치.

```bash
# 원격 설치
pip install git+https://github.com/DXR-keonghun6612/ToolBox.git@HUB#subdirectory=폴더명

# 로컬 설치
pip install -e . --config-settings editable_mode=compat
```

---

## 개발 로그

| 날짜 | 대상 | 내용 |
| --- | --- | --- |
| 2026-06-15 | `python_toolbox/file` | `dispatch.py` → `__init__.py` 병합, `Make_dict_from`/`Make_list_from` 추가, `_csv.py` 구현 |
| 2026-06-15 | `torch_toolbox` | 중앙 `registry.py`/`typing.py` 삭제 → 각 서브모듈 `__init__`으로 분산, `Runtime_init` 시그니처 변경 |
| 2026-09-08 | `ui_toolbox` | 패키지 신설. 칸·캔버스·진행 세 주제, 주제 안은 선언/위젯/배치 세 층 |
