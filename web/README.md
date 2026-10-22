# web/ — 아티팩트 소스

## `unui-sigantable.html` — 운의 시간표

이번 주·다음 주, 이번 달·다음 달, 올해·내년의 운을 **12신살·십이운성·지지 관계**로 읽는 만세력 지면.
Claude의 Artifact로 게시해 쓰며, 매일 아침 Routine이 `DAILY` 블록만 새로 써서 같은 URL에 재게시한다.

> ⚠️ 이 폴더는 **스킬 본문이 아니다.** 스킬로 업로드할 때는 `SKILL.md`·`references/`·`scripts/`만 필요하다.

### 페이지가 담고 있는 것

- 표 구획(`GENERATED:TABLES`) — 장간·관계·신살 표, 절기표, Asia/Seoul 시간대 이력을 `scripts/build_web_tables.py`가 `saju_calc.py`에서 생성한다. **손으로 고치지 않는다.**
  - 절기표: 1900 입춘 ~ 2046 소한, KST 눈금 **밀리초**(올림) 단위 delta·base16 — 페이지는 분으로 환산해 쓴다 (`sun_lon()` 겉보기 황경 of-date + ΔT 보정, errata #14·#22)
  - 시간대: 1908년 이전 지방시, 1908~1911·1954~1961 UTC+8:30, 서머타임 연도를 벽시계 입력에서 자동 적용 (Python zoneinfo fold=0과 같은 선택, errata #23)
- 사주 산출: 입춘 기준 연주 / 절입 기준 월주(출생 **순간**으로 비교) / 1900-01-01=甲戌 기준 일주(23시 초과 익일) / 시두법 시주 / 서울 경도 보정(지방평균시)은 시주와 23시 일주 경계에만 (errata #18)
- 격 1차 후보: 월령 본기 우선, 건록·양인·월겁·잡기 별도 (`saju_calc.gyeok_candidates()`와 같은 규칙, errata #20)
- `references/29_sibisinsal.md` 12신살(년지·일지 기준 병기)
- `references/30_shinsal_extended.md` 십이운성(음포태·양포태 병기), 개별 신살 조견표
- `references/22_hapchung_shinsal.md` 합·충·형·파·해 + 원진·귀문·격각
- `references/31_unse_narrative.md` 3층 서술 구조와 서술 규범

격국·용신의 성패 판정은 담지 않는다. **격 1차 후보**까지만 표시하고, 그 사실을 페이지에 밝힌다.

### 표 갱신과 검증

```bash
python3 scripts/build_web_tables.py          # saju_calc.py 표가 바뀌면 HTML 표 구획을 다시 생성
python3 scripts/build_web_tables.py --check  # 구획이 최신인지 (CI)
python3 tests/build_fixtures.py              # 계산 규칙을 일부러 바꿨을 때만 픽스처 재생성
node --test tests/*.test.mjs                 # 웹 엔진 ↔ Python 픽스처 교차검증
```

`tests/web_parity.test.mjs`는 `tests/fixtures/natal_cases.json`의 38개 명조(1900~2044년생 — LMT·UTC+8:30·서머타임 공백/중복 시각·절입 직후·자시 경계 포함)에서
**4기둥 · UTC 오프셋 · 서머타임 · 경도 보정 · 대운 방향·대운수·간지 10개·교체 연월 · 12신살 · 공망 · 십이운성 · 격 후보**가 Python과 같은지,
24번 원전 명조 전부에서 격 후보가 같은지, 현재 대운 선택·시각 모름/보정 경계 경고가 맞는지 본다.
`tests/web_render.test.mjs`는 DOM 스텁 위에서 페이지 렌더(`boot()`)를 돌려 명조 6개가 오류 없이 그려지고 경고가 화면의 '확인' 칸에 나오는지 본다.

> 페이지의 `const` 선언은 그냥 `eval`로는 밖으로 새지 않는다. 테스트는 `new Function`으로 감싸 필요한 것만 돌려받는다.

### 갱신 구조

```
DAILY = { for, profile, title, body, act }   ← 매일 아침 이 블록만 교체된다
```

`for`가 오늘(KST)이 아니거나, 보는 사람이 다른 명식을 입력해 두었으면
페이지가 그 자리를 **엔진 계산값으로 자동으로 채운다.** 갱신이 하루 걸러도 비어 보이지 않는다.

생년월일시는 브라우저 `localStorage`에만 저장되며 어디로도 전송되지 않는다.
