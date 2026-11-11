# us-morning-brief

매일 아침 미국 시장 지수, 국채 금리, 연준 발표를 모아 보여주는 정적 웹페이지입니다.

## 동작 방식

1. GitHub Actions가 평일 한국시간 오전 7시에 `scripts/build.py`를 실행합니다.
2. 스크립트가 데이터를 받아 `docs/index.html`을 만듭니다.
3. 만들어진 `docs` 폴더가 GitHub Pages로 배포됩니다.

## 데이터 출처

| 항목 | 출처 |
|---|---|
| 지수 종가 | Stooq 일별 CSV |
| 국채 금리 | FRED(세인트루이스 연준) 일별 CSV |
| 연준 발표 | 연준 공식 RSS |

Stooq 이용 조건은 직접 확인해 주세요. 문제가 있으면 `scripts/build.py`의 `fetch_index`만 다른 제공처로 바꾸면 됩니다.

## 로컬에서 화면만 확인하기

```
python scripts/build.py --demo
```

네트워크 없이 샘플 데이터로 `docs/index.html`을 만듭니다.

## 처음 한 번 해야 할 설정

1. 저장소 Settings → Pages → Source를 **GitHub Actions**로 선택합니다.
2. Actions 탭 → **매일 브리핑 갱신** → **Run workflow**로 첫 실행을 합니다.

정보 제공용이며 투자 조언이 아닙니다.
