# backbone TODO

구조는 `README.md` 소유. 여기는 미완 항목과 열린 설계 질문.

## 논의 대상

### DINOv3 가중치

- 걸리는 것 : `_DINO_VARIANTS` 의 `v3_*` 가 Meta DINOv3 라이선스. DINOv2 (Apache-2.0) 와 다름
- 목표 : 상업 이용 가능한 가중치만 (ConvNeXt V2 를 뺀 기준)
- 갈래 : 전부 제거 / 조건 확인 후 유지 / 제약을 주석으로만
- 정해지는 조건 : DINOv3 라이선스 원문 확인

### 백본 계약에 입력 크기가 없음

- 걸리는 것 : ViT 계열은 빌드 시 `img_size` 로 pos-embed 를 굽는데 계약 (`Out_channels`, `Feature_strides`,
  `forward`) 에 그 값이 없음. 소비처 (`Segmentor._Validate_backbone`) 가 `backbone.backbone.patch_embed.img_size`
  를 직접 뒤지고, 그 경로를 맞추려 conv 인코더가 가짜 `.backbone` 속성을 둠
- 목표 : 소비처가 래퍼 내부 구조를 모름. 계약 메서드만
- 갈래 : `Input_size() -> tuple[int, int] | None` 추가, conv 계열은 None / 래퍼가 빌드 시 `img_size` 를 받아 스스로 검증
- 정해지는 조건 : ViT 백본이 다시 쓰이는지. 지금 소비처는 `residual_encoder`, `convnext` 뿐

## 합의 사항

### 백본 래퍼는 쓰는 것만

- 현재 : `dino`, `convnext`, `resnet`
- 되살리는 비용 : `Timm_Feature_Backbone` 상속 + `VARIANTS` 맵 + Config 세 줄
- 되살릴 때 확인 : timm 모델명, 태그 유효성 (`timm.list_pretrained(arch)`. 버전마다 바뀜), 가중치 라이선스
