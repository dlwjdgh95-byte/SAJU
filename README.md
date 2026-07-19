# saju-expert 스킬

명리학(사주) 전문가 Claude 스킬. 자평진전(격국)·궁통보감(조후)·적천수(강약)를 기반으로 한 학문적 사주 해석 스킬입니다.

이 저장소는 **두 가지 방식**으로 사용할 수 있습니다.

---

## 방법 A — 스킬 직접 업로드 (스냅샷)

저장소 루트(`SKILL.md` + `references/` + `scripts/`)가 **완결형 전체 스킬**입니다.

- **사용처**: claude.ai(Claude 홈) → 설정 → Skills 에 이 폴더를 업로드
- **장점**: 별도 커넥터 없이 그 자체로 완전 동작
- **단점**: GitHub를 업데이트해도 **자동 반영 안 됨** → 수정할 때마다 다시 업로드해야 함

```
/                       ← 방법 A: 이 루트 전체가 스킬
├── SKILL.md            (원본, 전체 로직)
├── references/         (28개 상세 자료)
└── scripts/saju_calc.py
```

---

## 방법 B — GitHub 실시간 연동 (권장)

`github-linked/` 폴더의 **얇은 스킬**을 사용합니다. 핵심 원리·라우팅·Errata만 담고, 상세 자료는 **매번 이 GitHub 저장소에서 최신본을 읽어옵니다.**

- **사용처**: claude.ai에 (1) **GitHub 커넥터** 연결 + (2) `github-linked/` 폴더를 스킬로 업로드
- **장점**: **이 저장소의 `references/`·`scripts/`를 수정하면 대화에 곧바로 반영됨** (다시 업로드 불필요)
- **단점**: GitHub 커넥터가 켜져 있어야 하고, 파일을 그때그때 불러오므로 약간 느림

```
github-linked/
└── SKILL.md            ← 방법 B: 얇은 로더. references/·scripts/는 GitHub에서 읽음
```

### 설정 순서

1. claude.ai → 설정 → 커넥터 → **GitHub 연결** (이 저장소 `dlwjdgh95-byte/SAJU` 접근 허용)
2. claude.ai → 설정 → Skills → `github-linked/` 폴더를 스킬로 등록
3. 대화에서 사주 질문 → 스킬이 트리거되면 GitHub `main` 브랜치의 필요한 파일을 읽어 분석

> 이후 사주 자료를 보강하려면 이 저장소의 `references/` 파일이나 `scripts/saju_calc.py`를 고쳐 `main`에 병합하기만 하면 됩니다. 얇은 스킬은 그대로 두어도 최신 자료를 읽어옵니다.

---

## 두 방법 비교

| | 실시간 GitHub 연동 | 커넥터 필요 | 자료 수정 시 |
|---|---|---|---|
| **A. 루트 업로드** | ❌ | 불필요 | 스킬 재업로드 |
| **B. github-linked** | ✅ | 필요(GitHub) | 재업로드 불필요 |

두 스킬은 동일한 `name: saju-expert`와 트리거를 갖습니다. **둘 중 하나만 등록**하세요(동시 등록 시 중복).

---

## 파일 구성

- `SKILL.md` — 방법 A용 전체 스킬 본문
- `github-linked/SKILL.md` — 방법 B용 얇은 로더
- `references/01~10` — 궁통보감 조후 (일간별)
- `references/11~18` — 격국 (십신별 格)
- `references/19~28` — 성패·강약·합충·학파이견·원전사례·병약론·수동계산·출력·점수화
- `scripts/saju_calc.py` — 간지·절기·대운·세운 결정론적 계산 (ephem)
