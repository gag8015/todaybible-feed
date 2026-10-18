# 오늘성경 날씨 파일 (weather_feed)

기상청 단기예보를 **하루 4번** 전국 시·군·구 격자마다 한 번씩 받아 `weather.json` 하나로 만들고 GitHub Pages에 올린다.
앱은 이 파일만 받는다 → 사용자가 10만 명이어도 기상청 호출은 하루 약 (격자 수 × 4)번으로 고정.
위치는 앱 안에서 격자 번호로만 바꿔 쓰고 밖으로 보내지 않는다(위치정보법 노출 없음). 서비스 키는 GitHub 비밀값에만 있고 앱에는 없다.

## 처음 한 번 설정 (사용자 계정 필요)
1. **공공데이터포털**(data.go.kr) 로그인 → "기상청_단기예보 조회서비스" 활용신청(자동 승인) → 마이페이지에서 **일반 인증키(Decoding)** 복사.
   - 같은 페이지 참고문서의 **격자_위경도 엑셀**을 받아 `python -I make_regions.py <엑셀>` → `regions.json` 생성.
2. **GitHub** 저장소 새로 만들기(공개, 예: `todaybible-feed`) → 이 폴더 내용을 그대로 올린다(`regions.json` 포함).
3. 저장소 Settings → Secrets and variables → Actions → New secret: 이름 `KMA_SERVICE_KEY`, 값 = 1번 키.
4. Settings → Pages → Source = **GitHub Actions**.
5. Actions 탭 → weather → **Run workflow** 로 한 번 돌려 보기 → `https://<계정>.github.io/<저장소>/weather.json` 열리면 성공.
6. 앱 원격 설정(`remote_config.sample.json`)에 `"weather_url": "https://<계정>.github.io/<저장소>/weather.json"` 추가 → 드라이브 파일 "새 버전 업로드".
   앱은 다음 설정 갱신(최대 6시간) 뒤부터 기상청 날씨를 쓰고, 설정에 "날씨 지역" 고르기가 나타난다. 파일이 없거나 실패하면 MET Norway로 자동 전환.
7. (권장) 원격 설정도 이 저장소의 `site/config.json`으로 옮기면 드라이브 다운로드 한도 걱정이 없다 → 다음 앱 업데이트에서 `ProductionAds.CONFIG_URL`을 Pages 주소로 변경.

## 파일
- `fetch_kma.py` — 기상청 호출·요약·`site/weather.json` 쓰기. 실패 30% 넘으면 기존 파일 유지(배포 안 함).
- `test_fetch.py` — 네트워크 없이 요약 로직 검사(Actions에서 먼저 실행).
- `make_regions.py` — 기상청 격자 엑셀 → `regions.json`.
- `.github/workflows/weather.yml` — KST 05:20·11:20·17:20·23:20 자동 실행 + Pages 배포.
- `site/config.json` — 앱 원격 설정 사본(옮길 때 사용).

## weather.json 모양
```json
{"updated":"2026-10-18T05:20+09:00","base":"20261018 0500","source":"기상청",
 "grids":{"60_127":{"t":14.0,"sky":4,"pty":1,"reh":80,"wsd":2.1,"at":"202610180600",
                    "today":{"max":22.0,"min":13.0,"pop":80,"rain":2.5,"pty":1},
                    "tomorrow":{"max":20.0,"min":11.0,"pop":20,"rain":0.0,"pty":0}}},
 "regions":[["서울특별시","종로구","60_127"]]}
```
SKY 1 맑음·3 구름많음·4 흐림, PTY 0 없음·1 비·2 비/눈·3 눈·4 소나기. 출처 표기: "날씨 정보: 기상청".
