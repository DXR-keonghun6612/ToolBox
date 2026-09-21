# backbone TODO

구조는 `README.md` 소유. 여기는 미완 항목과 열린 설계 질문.

## 논의 대상

### DINOv3 가중치

- 걸리는 것 : `_DINO_VARIANTS` 의 `v3_*` 가 Meta DINOv3 라이선스. DINOv2 (Apache-2.0) 와 다름
- 목표 : 상업 이용 가능한 가중치만 (ConvNeXt V2 를 뺀 기준)
- 갈래 : 전부 제거 / 조건 확인 후 유지 / 제약을 주석으로만
- 정해지는 조건 : DINOv3 라이선스 원문 확인

## 합의 사항

### 백본 계약에 입력 크기를 안 둠

- 계약은 `Out_channels`, `Feature_strides`, `forward` 셋. 입력 크기는 소비처가 export 시점에만 앎
- ViT 래퍼는 `dynamic_img_size=True`. pos-embed 를 forward 마다 새 격자로 보간 - 토큰 수가
  입력 크기를 따라 변하고 patch 크기는 고정 (patch-embed 가중치)
- 학습 격자와 크게 다른 입력은 보간 근사라 품질이 떨어질 수 있음. 막지는 않음
- 소비처가 `backbone.backbone.patch_embed` 를 뒤지는 검사, 그 경로를 맞추려던 conv 인코더의
  가짜 `.backbone` 속성은 없앰

### 백본 래퍼는 쓰는 것만

- 현재 : `dino`, `convnext`, `resnet`
- 되살리는 비용 : `Timm_Feature_Backbone` 상속 + `VARIANTS` 맵 + Config 세 줄
- 되살릴 때 확인 : timm 모델명, 태그 유효성 (`timm.list_pretrained(arch)`. 버전마다 바뀜), 가중치 라이선스

## 진행 계획

- [ ] `dino.py` : `timm.create_model` 에 `dynamic_img_size=True`. `timm_kwargs.img_size` 는
      pos-embed 초기 격자로만 남음. 학습 크기와 다른 입력으로 forward 되는지 확인
