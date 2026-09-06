# web/ — 아티팩트 소스

## `unui-sigantable.html` — 운의 시간표

이번 주·다음 주, 이번 달·다음 달, 올해·내년의 운을 **12신살·십이운성·지지 관계**로 읽는 만세력 지면.
Claude의 Artifact로 게시해 쓰며, 매일 아침 Routine이 `DAILY` 블록만 새로 써서 같은 URL에 재게시한다.

> ⚠️ 이 폴더는 **스킬 본문이 아니다.** 스킬로 업로드할 때는 `SKILL.md`·`references/`·`scripts/`만 필요하다.

### 페이지가 담고 있는 것

- 절기표(1900 입춘 ~ 2046 소한, KST 분 단위) 내장 — `scripts/saju_calc.py`의 `sun_lon()`(겉보기 황경 of-date, errata #14 교정본)으로 산출한 값을 delta·base16으로 인코딩
- 사주 산출: 입춘 기준 연주 / 절입 기준 월주 / 1900-01-01=甲戌 기준 일주(23시 초과 익일) / 시두법 시주 / 진태양시 −32분
- `references/29_sibisinsal.md` 12신살(년지·일지 기준 병기)
- `references/30_shinsal_extended.md` 십이운성(음포태·양포태 병기), 개별 신살 조견표
- `references/22_hapchung_shinsal.md` 합·충·형·파·해 + 원진·귀문·격각
- `references/31_unse_narrative.md` 3층 서술 구조와 서술 규범

격국·용신의 성패 판정은 담지 않는다. 월지 투출 기준 **격 1차 후보**까지만 표시하고, 그 사실을 페이지 하단에 밝힌다.

### 검증

JS 엔진은 `scripts/saju_calc.py`와 30개 명조(1920~2044년생, 절입 경계·자시 경계 포함)에서
**사주 4기둥 · 대운수 · 대운 첫 간지 · 12신살 · 공망**이 전부 일치함을 교차확인했다.

```bash
node - <<'EOF'
const fs=require('fs');
const html=fs.readFileSync('web/unui-sigantable.html','utf8');
const src=html.slice(html.indexOf('<script>')+8, html.indexOf('/* ══ 렌더'));
const E=new Function(src+'; return {buildNatal,sinsal12,unseong,relationsTo,dayPillar,kmin,nowKd};')();
console.log(E.buildNatal({date:'1995-10-29',time:'06:30',timeKnown:true,gender:'M'}).pillars.join(' '));
EOF
```

> 페이지의 `const` 선언은 그냥 `eval`로는 밖으로 새지 않는다. 위처럼 `new Function`으로 감싸 필요한 것만 돌려받는다.

### 갱신 구조

```
DAILY = { for, profile, title, body, act }   ← 매일 아침 이 블록만 교체된다
```

`for`가 오늘(KST)이 아니거나, 보는 사람이 다른 명식을 입력해 두었으면
페이지가 그 자리를 **엔진 계산값으로 자동으로 채운다.** 갱신이 하루 걸러도 비어 보이지 않는다.

생년월일시는 브라우저 `localStorage`에만 저장되며 어디로도 전송되지 않는다.
