# transform TODO

구조는 `README.md` 소유. 여기는 미완 항목과 열린 설계 질문.

## 합의 사항

### 마스크 입력 dtype

- 입력은 uint8 (1, 1, H, W). 호스트 -> 엔진 전송이 float32 의 1/4
- 캐스팅은 toolbox 첫 연산. TRT 가 uint8 을 입출력 텐서로만 허용하므로 첫 연산이기만 하면
  어느 쪽이든 되는데, 소비처 래퍼에 남는 연산이 없어 여기가 자연스러움

### 주축 방향의 180도 확정

- 지금은 `flip_phase_deg` 로 한쪽을 골라 하나만 냄. 대칭 형상에서는 그 선택이 노이즈
  (`Frame.anisotropy`, `Frame.flip_margin` 이 그 미결정성을 보고)
- 두 자세를 다 내는 쪽이 거의 공짜. 재샘플링 없이 첫 자세에서 도출됨 (실측 확인, 아래 전부
  비트 일치 또는 FP32 노이즈)
  - `radial_rle` : theta 축 `NT/2` circular roll
  - `region` : 위치 2항 (`centroid_du`, `centroid_dv`) 부호 반전. 크기 7 + 비율 5 는 불변
  - `moment` : 6항 전부 부호 반전 (카이랄 2, 3차 모멘트 4 - 전부 홀수차)
  - `angle` : `+ pi`. `occupancy`, `center`, `anisotropy`, `flip_margin` 불변
- 지금 안 함. 소비처가 두 자세를 필요로 할 때 넣음 - 그때는 `flip_phase_deg` 부품별 표도 불필요

### `old/`

- 되살릴 때 layer / functional 기준으로 새로 옮겨 씀

## 진행 계획

- [ ] 방향 검사, ONNX 검증 (함수마다 export -> onnxruntime allclose + op 목록 대조), `px_size`
      스케일 불변 (확대 마스크 대조) 을 테스트로. 지금은 전부 일회성 실행. 테스트 폴더 없음
- [ ] FP16 검증 : `Local_contrast` 의 `E[v^2] - E[v]^2` 상쇄 오차
- [ ] 마스크 입력 uint8 캐스팅 (위 합의)
