# TODO

구조는 `README.md` 소유. 여기는 여러 축에 걸친 미완 항목과 열린 설계 질문. 축 하나의 것은 그 폴더의 `TODO.md`.

## 논의 대상

### config 기반 위상 조립기

- 걸리는 것 : `Build_from_registry` 는 조립만 하고 데이터 흐름 (위상) 은 forward 코드가 가짐 ->
  특정 조합을 코드로 박은 용접 클래스가 위상을 하드코딩
- 목표 : config 가 layer 위상 (여러 입력, 분기) 을 선언하면 그대로 잇는 범용 조립 모듈
- 갈래 : LENS `process` 의 ctx/Stage 엔진을 공유로 올림 / torch_toolbox 자체 조립기
- 정해지는 조건 : "core 연산 엔진 공유" 논의의 결론
- 적용 대상 : transform 조립 (frame -> `Radial` -> 측정 -> 토큰), 학습 그래프 (토큰 -> 헤더)

### `${경로}` 참조 해석의 구현

- 걸리는 것 : 아래 합의 "config 조립" 의 참조 문법을 무엇으로 푸는지 미정
- 목표 : 파일 병합 + 경로 참조 + 순환 참조 검출 + 출처가 드러나는 오류 메시지
- 갈래 : OmegaConf 의존 (interpolation 그대로) / `python_toolbox` config 로더에 자체 해석기
- 정해지는 조건 : 병합, 경로 참조 외에 필요한 기능이 있는지 (구조화 검증, 덮어쓰기 CLI)

## 합의 사항

### config 조립

- 최상위 config 가 파일 경로로 여러 config 를 읽어 트리 하나로 병합. 파일은 묶음 단위 (데이터, 모델, loss, optim, runtime)
- 사실 하나에 소유 config 하나. 나머지는 참조만
- 참조는 config 가 선언 : `${경로}` (예 `input_size: ${data.input_size}`). assembler 는 참조를 푸는 범용 코드, 발췌 규칙을 모름
- 실행 중에야 아는 값 (데이터 내용에서 나오는 `num_classes` 등) 은 기존 `$키` context. config 사실은 `${경로}`, 실행 중 값은 `$키`
- 저장되는 run config 는 병합, 해석을 마친 트리 하나
- `shared` (모든 Config 에 공통 필드 덮어쓰기) 와 `Resolve_config` 의 경로 로드는 이것으로 대체

### export

- export 정책 (opset, precision, workspace, external_data, 동적 축 범위) 은 runtime config
- dataset 은 입력 명세 (이름, dtype, shape) 와 필요하면 앞단 모듈만. 자기 config 에서 유도, 새로 적는 값 없음
- dummy 는 runner 가 입력 명세로 생성. 값은 무관, shape, dtype 만
- 출력 이름, 프로파일은 probe (dummy 한 번 실행) 에서
- 파일 이름 `{project}_{name}_{precision}`. `name` = export 되는 객체의 `.name`, 병합이면 모델 `.name`

## 진행 계획

### config, export

- [ ] 참조 해석 구현 (위 논의 결론 뒤). 병합, `${경로}`, 순환 검출, 해석된 트리 저장
- [ ] assembler 가 병합 트리를 받도록. `shared`, `Resolve_config` 경로 로드 제거
- [ ] export 헬퍼 : 입력 명세 + 정책 -> dummy, 프로파일, probe, 파일 이름. `Custom_Dataset.Info_for_onnx` 계약을 입력 명세로

### 테스트

- [ ] 테스트 폴더 자체가 없음. 자리와 실행 방식부터
- [ ] `runner/assembler` : mode 별 `Assemble_Metric` 빌드, `Update/Finalize` 흐름
- [ ] `metric/component` : Scalar/Centroid/Assemble accumulator 단위
- [ ] `runner/supervised` : `_Iter_hook` -> `_Forward` -> `metric[mode].Update` -> `log_batch` 통합

### 배포

- [ ] ONNX 추출 후 무결성 검증 (`onnx.checker.check_model()`)
