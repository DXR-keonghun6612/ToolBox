# TODO

구조는 `README.md` 소유. 여기는 미완 항목과 열린 설계 질문만.

## 논의 대상

### config 기반 위상 조립기

- 걸리는 것 : `Build_from_registry` 는 조립만 하고 데이터 흐름(위상)은 forward 코드가 가짐 ->
  특정 조합을 코드로 박은 용접 클래스가 위상을 하드코딩
- 목표 : config 가 layer 위상(여러 입력, 분기)을 선언하면 그대로 잇는 범용 조립 모듈
- 갈래 : LENS `process` 의 ctx/Stage 엔진을 공유로 올림 / torch_toolbox 자체 조립기
- 정해지는 조건 : "core 연산 엔진 공유" 논의의 결론
- 적용 대상 : geometry 내부(frame -> polar -> radial -> descriptor -> 토큰), 학습 그래프
  (토큰 -> 헤더)

### geometry descriptor 의 config 선택

- 걸리는 것 : `Geometry_Embedding.Build` 가 sub-module 과 spec, concat 순서를 코드로 박음.
  descriptor 를 넣고 빼려면 코드 수정
- 목표 : 파이프라인(frame/coords/polar/radial)은 항상, descriptor 는 `sub_module_meta` 로 선택.
  forward 가 존재하는 descriptor 만 조립
- 갈래 : 위 위상 조립기 위에서 / `Build_from_registry` 만으로
- 정해지는 조건 : 위상 조립기 결론
- 같이 갈 것 : 한 모듈이 여러 중간값을 소비하는 경우(stats, fourier 류)의 입력 바인딩.
  지금 토큰 스키마에서는 제거라 당장 불필요
- 소비처 : LENS analysis 가 flat 출력을 가정 -> LENS `core/process/TODO.md`

### DINOv3 가중치

- 걸리는 것 : `_DINO_VARIANTS` 의 `v3_*` 가 Meta DINOv3 라이선스. DINOv2(Apache-2.0)와 다름
- 목표 : 상업 이용 가능한 가중치만 (ConvNeXt V2 를 뺀 기준)
- 갈래 : 전부 제거 / 조건 확인 후 유지 / 제약을 주석으로만
- 정해지는 조건 : DINOv3 라이선스 원문 확인

### `transform/mask` 의 "정준(canonical)"

- 걸리는 것 : `canonical.py`, `Frame`, README 가 유일한 대표 자세를 말하나 대칭 형상에서는
  불성립 (n >= 3 회전대칭이면 `Z2 = 0`, 2회 대칭이면 `Z3 = 0`). `anisotropy`, `flip_margin` 은
  미결정성을 보고할 뿐 없애지 못함. `Align_Raster` 서술만 "주축 정렬" 로 낮춤
- 목표 : 이름과 계약이 실제 보장과 일치
- 갈래 : 이름(`canonical.py`, `Frame`)까지 변경 / "정준" 을 비대칭 형상 한정으로 재정의
- 정해지는 조건 : 소비처가 미결정 케이스를 다루는 계약 - 임계로 회전 불변 거리로 내려갈지,
  두 자세를 다 내고 하류가 고를지. 지금은 값만 노출
- 같이 정할 것 : `flip_phase_deg` 부품별 표의 거처. 형상 상수인데 표는 소비처(413)가 들고
  toolbox 는 값만 받음

### 마스크 입력 dtype

- 걸리는 것 : 실루엣 사슬 입력이 float32 {0, 1}. 호스트 -> 엔진 전송이 uint8 의 4배
- 목표 : uint8 (1, 1, H, W) 입력
- 갈래 : toolbox 첫 모듈에서 캐스팅 / 소비처 래퍼에서 캐스팅
- 정해지는 조건 : TRT 는 uint8 을 입출력 텐서로만 허용 - 캐스팅이 첫 연산이면 어느 쪽이든 됨.
  소비처 래퍼가 리샘플(`rate`)을 갖게 되므로 그쪽이 자연스러움

## 합의 사항

### 실루엣 사슬 길이 상수 - `trust_radius` 하나

- 길이 단위는 기준 px 하나. `sampling_size`, `r_max`, `num_radial` 을 `trust_radius` 로 통합
- `trust_radius` (정수, 기준 px) : 이 반경 안은 1 px 간격으로 전부 읽고 밖은 안 읽음
- 유도 : `dr = 1`, `num_radial = trust_radius`, `norm = trust_radius` (FP16 무차원화 상수).
  셀 안 세부는 `sub` 가 맡음
- 캔버스 크기는 값에 안 남음. 오프셋 LUT 를 centroid 원점에 더해 읽을 뿐 (실증 : 280 캔버스와
  600x800 프레임에서 토큰 비트 단위 동일)
- `norm` 이 값에 남는 출력은 moment 뿐 (`_mu30` 계열이 원시 3차 모멘트, `norm^-3`).
  `Region_Scalars` 는 되곱해 상쇄. 상수 변경(197.28 -> trust_radius)은 소비처의 도메인
  나눗값으로 흡수
- 현장 배율 `(rate_h, rate_w)` (기준 카메라 1 px 가 현장 카메라에서 몇 px) 는 toolbox 밖 -
  소비처 래퍼가 입력 마스크를 기준 px 캔버스로 리샘플해 넣고 `center` 만 현장 px 로 되돌림.
  toolbox 는 기준 px 상수만 앎
- 걸리는 모듈 : `Centroid_Frame`, `Frame_Coords`, `Polar_Raster`, `Radial_Profile`, `Radial_RLE`,
  `Region_Scalars`, `Occupancy`, `Geometry_Embedding`, `image.py` 의 `Align_Raster`(frame 생성)

### geometry 토큰 스키마

- 출력은 토큰. flat `(B, D)` 는 `(B, 1, D)` 의 특수형
- 각도 시퀀스 `radial_rle` (NT, K) : theta 별 재료 밴드. centroid 가 구멍 안에 없어도 구멍 표현
- 전역 : `moment`(6), `area`(2), `ratio`(6), `size`(7), `position`(2)
- 제거 : radial_outer/inner, outer/inner/thickness/coverage_stats, spectral(fourier). 전부 radial
  프로파일 파생이라 rle 로 통일
- `K` 는 config 상수 (`Radial_RLE.max_transitions`)
- 조립(병합, 패딩)은 소비처 책임. `Features()` 가 도메인별 native 형태로 냄

### 백본 래퍼는 쓰는 것만

- 현재 : `dino`, `convnext`, `resnet`
- 되살리는 비용 : `Timm_Feature_Backbone` 상속 + `VARIANTS` 맵 + Config 세 줄
- 되살릴 때 확인 : timm 모델명, 태그 유효성(`timm.list_pretrained(arch)`. 버전마다 바뀜),
  가중치 라이선스

## 진행 계획

### `trust_radius` 통합 (`transform/mask`)

- [ ] 회귀 : 옛 상수(sampling_size 280, r_max 300, num_radial 360)와 대조. rle 는 dr 0.833 -> 1
      양자화 차이(반 px 이내), size/ratio/position 동일, moment 는 `(197.28 / trust_radius)^3` 배
- [ ] `Features()` 가 frame 을 함께 돌려주기. 소비처가 `frame()` 을 한 번 더 부름
- [ ] 순환 import : `occupancy` -> `geometry.spec` -> `geometry/__init__` -> `region` -> `occupancy`.
      `occupancy` 를 먼저 import 하면 실패. `geometry.spec` 을 `geometry/` 밖으로 빼거나
      `geometry/__init__` 이 하위를 지연 import

### geometry descriptor 선택 (위상 조립기 결론 뒤)

- [ ] descriptor 를 `sub_module_meta` 로 선언. forward 가 존재하는 것만 조립
- [ ] Normalizer(그룹별 선형 scale), `data_group_of`, `axis_of`, `Grouped` 를 토큰 축에 맞춤

### 테스트

- [ ] `runner/assembler` : mode 별 `Assemble_Metric` 빌드, `Update/Finalize` 흐름
- [ ] `metric/accumulator` : Scalar/Centroid/Assemble accumulator 단위
- [ ] `runner/supervised` : `_Iter_hook` -> `_Forward` -> `metric[mode].Update` -> `log_batch` 통합

### dataset

- [ ] data transform 의 `Get_transform()` if-else 를 registry 로
- [ ] Object Detection 데이터셋(COCO, YOLO). `coco.py`/`yolo.py` 스텁
- [ ] `dataloader/classification/image.py` : 이미지 외 입력(포인트클라우드, 센서)을 포괄하는
      classification dataset 구조

### modules

- [ ] Transformer 계열(Attention, Embedder) 리팩토링

### 배포

- [ ] ONNX 추출 후 무결성 검증 (`onnx.checker.check_model()`)
