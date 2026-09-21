# runner TODO

구조는 `README.md` 소유. 여기는 미완 항목.

## 합의 사항

### 조용한 skip 제거

누락을 기본 동작으로 흡수하지 않고 실패로 드러냄. 선택 사항이면 선언으로 받음.

- `assembler.py` `_Build_mode_data` : `mode_cfg` 에 없는 mode 는 skip. 실행에 필요한 mode (학습 TRAIN, 테스트 TEST) 가 없으면 실패
- `supervised/assembler.py` `_Restore_train_states` : 체크포인트에 `optim_state`, `scheduler_state`, `scaler_state` 가 없으면 skip,
  `_Load_checkpoint` 가 None 이면 복원 없이 반환. resume 인데 상태가 없으면 실패
