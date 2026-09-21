# modules TODO

구조는 `README.md` 소유. 여기는 미완 항목.

## 합의 사항

### 조용한 skip 제거

- `definition.py` `Composable_Module.Load_weights` : `strict=False` 로 키 불일치 레이어를 건너뜀. 부분 로드가 의도면
  허용 키 (prefix) 를 인자로 받고, 그 밖의 missing / unexpected 키는 실패
