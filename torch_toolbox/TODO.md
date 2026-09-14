# TODO

미완료 작업 목록. 완료 이력은 [README 개발 로그](./README.md#개발-로그) 참조.

---

## 후속 작업

### ★ 계획 — config 기반 **위상 조립기** (동적 그래프 조립 모듈)

용접 클래스(`Silhouette_Embedding` 등 특정 조합을 코드로 박은 것)를 없애고, **config 가 layer 위상을
선언하면 그대로 연결하는 범용 조립 모듈**을 둔다. 핵심은 단순 순차가 아니라 **위상(topology)** —
여러 입력·분기를 처리해 각 layer 를 config 가 정한 연결대로 잇는다(모델 그래프 구성).

- `Build_from_registry`(build.py)는 **조립(construction)만** 하고 런타임 데이터 흐름(위상)은 forward
  코드가 갖는다 — 그래서 지금은 용접 클래스가 forward 로 위상을 하드코딩한다. 이 조립기가 그 위상을
  **config 로** 받아 연결하면 용접이 사라진다.
- LENS `process` 의 ctx/Stage 엔진이 정확히 이 개념(유닛이 ctx 에서 꺼내 쓰고 route) — 공유로 올릴지,
  torch_toolbox 자체 조립기로 갈지 미결(→ 세션 초 "core 연산 엔진 공유" 논의와 같은 지점).
- 적용 대상: crop→resize→geometry 전처리, geometry 내부(frame→polar→radial→descriptor→토큰화),
  학습 그래프(geometry 토큰 → transformer 헤더). 지금은 용접 클래스/소비처 배선으로 임시.

### ★ geometry embedding — config 조립 + 토큰 출력 전환 (진행 중)

`transform/mask/geometry` 를 **config 기반 조립 + 토큰 시퀀스 출력**으로 재작성한다. 왜:

- **지금은 하드코딩** — `Geometry_Embedding.Build` 가 sub-module(frame·coords·polar·radial·region·
  moment·occ·stats·fourier)과 spec 리스트·concat 순서를 전부 코드로 박아, descriptor 를 넣고 빼려면
  코드를 고쳐야 한다. `Silhouette_Embedding` 은 config 조립(sub_module_meta)인데 geometry 내부만 monolith.
- **descriptor 는 이미 다 등록 모듈**(`centroid_frame`·`polar_raster`·`radial_rle`·`region_scalars`·
  `chirality_moments`·`fourier_descriptor` … MODELS 등록 확인됨). `Build_from_registry` 로 조립 가능 —
  build.py 는 조립만, 데이터 흐름(frame→polar→radial→descriptor)은 forward 코드가 표현(classification 이
  `cat(backbone, geometry)→header` 를 forward 로 잇듯이).

**출력 = 토큰 `(B, seq, 2K)`.** flat `(B, D)` 는 `(B, 1, D)` 인 토큰의 특수형이라 토큰이 일반형이다.
목표 토큰 스키마(합의됨):

- **각도 시퀀스**: `radial_rle` (512, 2K) — θ별 재료 밴드(살-구멍-살). centroid 위치 무관하게 구멍 표현
  (기존 radial_outer/inner 는 centroid 가 구멍 안에 있어야만 구멍이 보였다 — rle 가 대체).
- **전역 토큰(각 2K=8, 뒤 패딩)**: `moment`(6)·`area`(2)·`ratio`(6)·`size`(7)·`position`(2).
- **제거**: radial_outer/inner, outer/inner/thickness/coverage_stats, spectral(fourier mag/phase 전부).
  spectral 은 radial 프로파일의 Fourier(=중복), stats 도 프로파일 파생 → rle 로 통일.
- `K` 는 config 상수(`Radial_RLE.max_bands`, 기본 4). 2K = 토큰 차원.

**목적 — 토큰 기반 학습**: geometry 토큰 → transformer 헤더(기존 FC 헤더 대체, 더 압축적). 형상을
토큰이 다 담으므로 **DINOv2(ViT) 백본 제거** 가능(이미지 백본 없이 형상 토큰만으로 분류). 재학습 동반.

- [ ] descriptor 를 sub_module_meta 로 선언, 파이프라인(frame/coords/polar/radial)은 항상, descriptor 는
      config 선택. forward 가 **존재하는 descriptor 만 동적 조립**(고정 concat 제거).
- [ ] 출력 shape flat → 토큰 `(B, seq, 2K)`. Normalizer(그룹별 선형 scale)·`data_group_of`·`axis_of`·
      `Grouped` 를 토큰 축에 맞춰 갱신.
- [ ] stats/fourier 처럼 **한 모듈이 여러 입력**(r_outer/r_inner)에 쓰이던 것 — 토큰 스키마에선 제거라
      당장 불필요하나, 되살릴 땐 입력 바인딩(어느 중간값을 소비) 설계 필요.
- [ ] 소비처(LENS analysis: flat 가정) 토큰 대응 → LENS `core/process/TODO.md`.

---

## 테스트

- [ ] `runner/assembler` — mode별 `Assemble_Metric` 빌드 및 `Update/Finalize` 흐름 테스트
- [ ] `metric/accumulator` — Scalar/Centroid/Assemble accumulator 단위 테스트
- [ ] `runner/supervised` — `_Iter_hook` → `_Forward` → `metric[mode].Update` → `log_batch` 흐름 통합 테스트

---

## dataset

- [ ] YAML 파일 읽기 (`_Load_id_map` 등) — `python_toolbox` IO 유틸리티로 이전
- [ ] data transform — `Get_transform()` if-else 분기를 registry 구조로 교체
- [ ] Object Detection 데이터셋 파이프라인 완성 (COCO, YOLO) — coco.py/yolo.py 스텁 상태
- [ ] `dataloader/classification/image.py` — 이미지 외 입력(포인트클라우드, 센서 데이터 등)을 포괄하는 일반화된 classification dataset 구조로 개선 필요

---

## modules

- [ ] Transformer 계열 모듈 고도화 (Attention, Embedder 리팩토링)

### 합의 사항 — 백본 래퍼는 쓰는 것만 둔다

- 현재 : `dino` · `convnext` · `resnet`
- 되살리는 비용이 낮음 — `Timm_Feature_Backbone` 상속 + `VARIANTS` 맵 + Config 세 줄
- 되살릴 때 확인 : timm 모델명·태그 유효성 · 가중치 라이선스
- 태그 유효성은 눈으로 안 보임 — `timm.list_pretrained(arch)` 로 대조. timm 버전마다 태그가 바뀜

### 논의 대상 — DINOv3 가중치를 둘 것인가

- 걸리는 것 : `_DINO_VARIANTS` 의 `v3_*` 가 Meta DINOv3 라이선스. DINOv2(Apache-2.0)와 조건이 다름
- 목표 : 상업 이용 가능한 가중치만 남기기 (ConvNeXt V2 를 뺀 것과 같은 기준)
- 갈래 : 전부 제거 / 조건 확인 후 유지 / 제약을 주석으로만 남김
- 정해지는 조건 : DINOv3 라이선스 원문 확인

### 논의 대상 — `transform/mask` 의 "정준(canonical)" 이 과한 주장인가

`canonical.py` / `Frame` / README 의 "정준 좌표계" 는 **유일한 대표 자세가 있다**고 말하는데
대칭 형상에서는 성립하지 않는다 — n≥3 회전대칭이면 `Z2 = 0`, 2회 대칭이면 `Z3 = 0` 이라
각도가 원리적으로 미결정이고 출력은 노이즈가 정한 방향이다. `anisotropy` / `flip_margin` 은
그 미결정성을 **보고**할 뿐 없애지 못한다. `Align_Raster` 서술만 "주축 정렬" 로 낮췄다.

- 모듈·타입 이름(`canonical.py`, `Frame`)까지 바꿀 것인가, "정준" 을 *조건부*(비대칭 형상에
  한해)로 재정의하고 이름은 둘 것인가.
- 소비처가 미결정 케이스를 어떻게 다루는가 — 임계로 회전 불변 거리로 내려갈지, 두 자세를
  다 내고 하류가 고를지. 지금은 계약이 없고 값만 노출한다.
- `flip_phase_deg` 부품별 표의 거처. 형상이 정하는 상수인데 표는 소비처(413)가 들고
  torch_toolbox 는 값만 받는다 — 이 분리를 유지할지.

---

## 배포 파이프라인

- [ ] ONNX 추출 후 모델 무결성 검증 로직 추가 (`onnx.checker.check_model()`)

---

## 로깅 표준화

- [ ] `python_toolbox` 로거 도입 후 `definition.py` 내 `print` 교체 — python_toolbox 작업 완료 후 진행
