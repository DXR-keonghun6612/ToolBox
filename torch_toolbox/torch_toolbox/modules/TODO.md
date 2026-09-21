# modules TODO

구조는 `README.md` 소유. 여기는 미완 항목.

## 합의 사항

### `model/neck/` - 피라미드 결합 네 갈래

자리는 `model/neck/`. `backbone/` 과 같은 층 - 백본 타입을 모르고 단별 `(channels, strides)` 튜플만 앎.

- 방향 조합이 실제로 갈리므로 넷을 둠. 소비처는 코드가 아니라 config 로 고름
  - top-down : 깊은 단의 의미를 얕은 단으로 (FPN)
  - bottom-up : 얕은 단의 위치를 깊은 단으로
  - PAN (top-down -> bottom-up) : PANet 원형
  - PAN (bottom-up -> top-down) : 역순
- 공통 계약 : 단별 feature -> 공통 폭 `out_channels`, 단별 출력 + 최고해상 격자 (선택).
  `Out_channels()`, `Out_stride()`, 단별 stride
- 어느 단에서 도는지는 인자. 최고해상 단은 비싸서 빼는 경우가 많음
- 업샘플, 다운샘플 수단 (sub-pixel / 보간 / stride-2 conv) 과 홀수 크기 정합은 부품이 앎.
  결합 구조는 그것을 모름
- 소비처에 top-down 만 + 최고해상 하나만 내는 특수해가 있음. 올릴 때 일반해로 새로 씀

### 조용한 skip 제거

- `definition.py` `Composable_Module.Load_weights` : `strict=False` 로 키 불일치 레이어를 건너뜀. 부분 로드가 의도면
  허용 키 (prefix) 를 인자로 받고, 그 밖의 missing / unexpected 키는 실패
- `loss/definition.py` `Assemble_Loss.Build` : `sub_loss_coefs` 에 있으나 `sub_module_meta` 에 없는 키를
  무시함. 계수만 적고 모듈을 빠뜨리면 그 loss 가 계산 안 되는데 에러도 없음. 계수 키가 모듈 키에
  안 들면 raise. pred 에 없는 키를 건너뛰는 것 (선택 출력용) 은 별개라 그대로

## 진행 계획

- [ ] `model/neck/` 네 갈래 구현 (위 합의)
- [ ] `Assemble_Loss.Build` 계수 키 검사 (위 합의)
