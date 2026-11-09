# transform TODO

구조는 `README.md` 소유. 여기는 미완 항목과 열린 설계 질문.

## 합의 사항

### 마스크 입력 dtype

- 입력은 uint8 (1, 1, H, W). 호스트 -> 엔진 전송이 float32 의 1/4
- 캐스팅은 toolbox 첫 연산. TRT 가 uint8 을 입출력 텐서로만 허용하므로 첫 연산이기만 하면
  어느 쪽이든 되는데, 소비처 래퍼에 남는 연산이 없어 여기가 자연스러움

### 주축 방향

- `angle` 은 주축과 x 축 사이 각만. 주축 두 끝 중 어느 쪽인지는 안 가름 - 소비처 몫
- 반대 끝 자세는 재샘플링 없이 도출됨 (실측 확인, 아래 전부 비트 일치 또는 FP32 노이즈)
  - `radial_rle` : theta 축 `NT/2` circular roll
  - `region` : 위치 2항 (`centroid_du`, `centroid_dv`) 부호 반전. 크기 7 + 비율 5 는 불변
  - `moment` : 6항 전부 부호 반전 (카이랄 2, 3차 모멘트 4 - 전부 홀수차)
  - `angle` : `+ pi`. `occupancy`, `center`, `anisotropy` 불변

### `old/`

- 되살릴 때 layer / functional 기준으로 새로 옮겨 씀

## 진행 계획

- [ ] 방향 검사, ONNX 검증 (함수마다 export -> onnxruntime allclose + op 목록 대조), `px_size`
      스케일 불변 (확대 마스크 대조) 을 테스트로. 지금은 전부 일회성 실행. 테스트 폴더 없음
- [ ] FP16 검증 : `Local_contrast` 의 `E[v^2] - E[v]^2` 상쇄 오차
- [ ] 마스크 입력 uint8 캐스팅 (위 합의)
