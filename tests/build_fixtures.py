#!/usr/bin/env python3
"""
build_fixtures.py — 교차검증 명조 픽스처(tests/fixtures/natal_cases.json)를 saju_calc.py로 다시 만든다.
24번 원전 명조 86命의 격 후보도 함께 넣는다(웹 엔진 격 규칙 검사용).

Python 테스트(test_calc.py)는 현재 계산이 이 파일과 같은지, Node 테스트(web_parity.test.mjs)는
웹 엔진이 이 파일과 같은지 본다. 계산 규칙을 일부러 바꿨을 때만 다시 만들고, 바뀐 줄을 리뷰한다.

  python3 tests/build_fixtures.py
  python3 tests/build_fixtures.py --johu     # 궁통보감 고정 파일(johu_quotes.json·johu_docs.json)만 (--quotes도 같다)

--johu는 johu_wonmun.json 인용과 01~10번 그 달 '원문' 줄의 「」 인용(johu_quotes.json, errata #39), 01~10번 본문을
절(##·###) 단위로(johu_docs.json, errata #40) 고정한다. 01~10번을 일부러 고쳤을 때만 다시 만들고(원문 근거를 errata에 적는다),
git diff로 바뀐 줄을 리뷰한다. 본문 산문의 순서 표기는 검사기가 다 읽지 못하므로(확인 권장으로만 낸다) 되돌림은 이 고정이 잡는다.
다시 만든 뒤 check_consistency의 궁통보감 검사 결과(실패·확인 권장)를 함께 보여 준다.
"""

import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import saju_calc as S  # noqa: E402

OUT = os.path.join(HERE, "fixtures", "natal_cases.json")
QUOTES = os.path.join(HERE, "fixtures", "johu_quotes.json")
DOCS = os.path.join(HERE, "fixtures", "johu_docs.json")

# (날짜, 시각, 성별, 메모) — 입력은 그때 그 지역(서울) 벽시계 시각
CASES = [
    ("1995-10-29", "06:30", "M", "저장소 기본 예시 명조"),
    ("2000-01-01", "12:00", "M", "일주 기준점 2000-01-01 = 戊午"),
    ("1900-02-10", "12:00", "F", "표 시작 직후 (LMT 시대)"),
    ("1905-03-01", "12:00", "M", "LMT UTC+8:27:52 시대"),
    ("1910-06-01", "08:00", "F", "1908~1911 UTC+8:30"),
    ("1912-01-01", "01:30", "M", "UTC+9 전환 직후"),
    ("1920-07-15", "14:20", "F", "일반"),
    ("1945-08-15", "12:00", "M", "일반"),
    ("1950-04-01", "00:30", "M", "서머타임 시작 공백 시각(00:00~01:00, fold=0)"),
    ("1950-07-20", "09:10", "F", "서머타임 기간"),
    ("1958-01-15", "12:00", "F", "1954~1961 UTC+8:30"),
    ("1960-06-15", "12:00", "M", "UTC+8:30 + 서머타임 = UTC+9:30"),
    ("1961-08-10", "00:15", "M", "UTC+8:30→9 전환 공백 시각(00:00~00:30, fold=0)"),
    ("1970-03-06", "02:00", "F", "경칩 부근"),
    ("1987-05-10", "02:30", "F", "서머타임 시작 공백 시각(02:00~03:00, fold=0)"),
    ("1987-10-11", "02:30", "M", "서머타임 종료 중복 시각(fold=0 → 서머타임 쪽)"),
    ("1988-07-01", "10:00", "F", "서머타임 기간"),
    ("1999-12-31", "23:40", "M", "보정 후 23:08 → 익일 일주"),
    ("2000-01-07", "23:32", "M", "보정 후 23:00 정각 → 亥시·당일"),
    ("2000-01-07", "23:33", "F", "보정 후 23:01 → 子시·익일"),
    ("2000-01-07", "23:50", "M", "자시 정설 익일"),
    ("2010-05-05", "07:33", "F", "보정 후 07:01 → 辰시"),
    ("2010-05-05", "07:32", "M", "보정 후 07:00 정각 → 卯시"),
    ("2024-02-29", "12:00", "F", "윤년 2/29"),
    ("2025-01-05", "11:40", "M", "소한 직후 (전년 절기년 丑월)"),
    ("2026-02-04", "04:50", "F", "입춘 직전 → 乙巳년"),
    ("2026-02-04", "05:30", "F", "입춘 28분 후 → 丙午년 (P0-1 회귀)"),
    ("2026-02-04", "05:30", "M", "입춘 28분 후 남명 대운"),
    ("2026-09-07", "23:40", "M", "백로 1분 전 → 申월"),
    ("2026-09-07", "23:50", "M", "백로 9분 후 → 酉월 (P0-1 회귀)"),
    ("2026-12-07", "12:10", "F", "대설 직후"),
    ("2030-11-20", "18:45", "M", "미래"),
    ("2044-06-30", "03:15", "F", "표 끝 부근"),
    ("2034-02-04", "03:41", "F", "입춘 03:41:00.8 — 같은 분 출생은 절입 전 (초 내림 회귀)"),
    ("2005-06-05", "23:02", "M", "망종과 같은 분 출생"),
    ("1991-05-06", "09:27", "F", "입하와 같은 분 출생"),
    ("2023-08-12", "15:23", "M", "정밀 대운수 1.4999… → 1 (반올림 경계)"),
    ("1985-11-30", "10:00", "F", "대운 교체 연도 — 출생 연도+대운수 근사와 1년 차"),
]

# 시각 모름 (날짜, 성별, 메모) — 정오로 연·월·일주, 시주 없이 분석. 웹 buildNatal(timeKnown:false)과 대조
UNKNOWN_CASES = [
    ("1980-02-07", "M", "시주를 넣으면 寅午戌 회국이 생긴다 — 빼야 웹과 같다"),
    ("1980-02-08", "F", "시간 甲이 본기 투출로 잡혀 변화 후보를 가린다 — 빼야 웹과 같다"),
    ("1987-07-01", "M", "서머타임 — 00:00~00:32 전날 일주"),
    ("1958-07-01", "F", "UTC+8:30·서머타임 — 00:00~00:02 전날 일주"),
    ("1955-09-08", "M", "서머타임 종료일 — 23시대가 두 번 있다"),
    ("1910-06-01", "F", "UTC+8:30 — 23:03부터 익일 일주"),
    ("1905-03-03", "M", "지방시(LMT) — 23:01부터 익일 일주"),
    ("2026-02-04", "F", "입춘일 — 연주·월주 미정"),
    ("2026-03-15", "M", "보통 날 — 23:33부터 익일 일주"),
    ("1948-06-01", "F", "서머타임 시작일 — 00시대가 없다(경계 줄 없음)"),
    ("1961-08-10", "M", "UTC+8:30 → +9 전환일 — 00:00~00:29가 없다"),
]


def compute_unknown(date, gender):
    from datetime import datetime
    day0 = datetime.strptime(date, "%Y-%m-%d")
    t = S.resolve_time(day0.replace(hour=12))
    pillars, minfo = S.four_pillars(t["utc"], t["local"], "next")
    p3 = pillars[:3]
    dw = S.daewoon(p3, gender, t["utc"], minfo)
    sc = S.unknown_time_scan(day0)
    return {"pillars": p3, "gyeok": gyeok_names(p3), "oheng": S.analyze_pillars(p3)["oheng_count"],
            "day_alt": [list(x) for x in sc["alt"]], "amb": list(sc["amb"]) if sc["amb"] else None, "amb_gap": sc["gap"],
            "amb_alt": [list(x) for x in sc["amb_alt"]],
            "daewoon": {"start_age": dw["start_age"], "list": [x["ganzhi"] for x in dw["list"]]}}


def compute(date, time, gender):
    from datetime import datetime
    wall = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    t = S.resolve_time(wall)
    pillars, minfo = S.four_pillars(t["utc"], t["local"], "next")
    dw = S.daewoon(pillars, gender, t["utc"], minfo)
    yz = pillars[0][1]
    return {
        "pillars": pillars,
        "offset_min": t["offset_min"], "dst_min": t["dst_min"], "corr_min": t["corr_min"],
        "local": f"{t['local']:%Y-%m-%d %H:%M}",
        "daewoon": {"direction": dw["direction"], "start_age": dw["start_age"],
                    "list": [x["ganzhi"] for x in dw["list"]],
                    "start": [x["start"] for x in dw["list"]]},
        "sinsal12_year": [S.sibisinsal(yz, p[1]) for p in pillars],
        "gongmang": S.gongmang(pillars[2]),
        "unseong_eum": [S.unseong(pillars[2][0], p[1]) for p in pillars],
        "gyeok": gyeok_names(pillars),
    }


def gyeok_names(pillars):
    return [x["격"] for x in S.gyeok_candidates(pillars)["후보"]]


def corpus():
    """24번 원전 명조 전부의 격 후보 — 웹 엔진 격 규칙 검사용."""
    import re
    rows = []
    for l in open(os.path.join(HERE, "..", "references", "24_japyeong_cases.md"), encoding="utf-8"):
        m = re.match(r"^### (\S+)\. .*?〔(.+?)〕", l)
        if m:
            ps = m.group(2).split()
            rows.append({"id": m.group(1), "pillars": ps, "gyeok": gyeok_names(ps)})
    return rows


def build():
    rows = []
    for date, time, gender, memo in CASES:
        rows.append({"date": date, "time": time, "gender": gender, "memo": memo,
                     "expect": compute(date, time, gender)})
    unknown = [{"date": date, "gender": gender, "memo": memo, "expect": compute_unknown(date, gender)}
               for date, gender, memo in UNKNOWN_CASES]
    return {"_note": "saju_calc.py 기본 옵션(Asia/Seoul·서울 경도·LMT·자시 정설) 기준. tests/build_fixtures.py로 생성",
            "cases": rows, "unknown": unknown, "corpus": corpus()}


def johu_quotes():
    """{일간: {월지: {"quote": json 인용, "wonmun": 그 달 '원문' 줄의 「」 인용 목록}}}."""
    import glob, re
    ref = os.path.join(HERE, "..", "references")
    with open(os.path.join(ref, "johu_wonmun.json"), encoding="utf-8") as f:
        table = json.load(f)["table"]
    files = sorted(glob.glob(os.path.join(ref, "0[1-9]_gungbok_*.md"))) + sorted(glob.glob(os.path.join(ref, "10_gungbok_*.md")))
    out = {}
    for g, path in zip(S.GAN, files):
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        heads = list(re.finditer(r"^### .*?\(([子丑寅卯辰巳午未申酉戌亥])月生\)", txt, re.M))
        secs = {h.group(1): txt[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(txt)] for i, h in enumerate(heads)}
        out[g] = {}
        for z in S.MONTH_ZHI:
            wl = re.search(r"^\*\*원문 \(窮通寶鑑\)\*\*: (.+)$", secs.get(z, ""), re.M)
            out[g][z] = {"quote": table[g][z]["quote"], "wonmun": re.findall(r"「([^」]+)」", wl.group(1) if wl else "")}
    return out


def johu_files():
    import glob
    ref = os.path.join(HERE, "..", "references")
    return sorted(glob.glob(os.path.join(ref, "0[1-9]_gungbok_*.md"))) + sorted(glob.glob(os.path.join(ref, "10_gungbok_*.md")))


def johu_docs():
    """{파일: {"절 제목": 해시}} — 01~10번 본문을 ##·### 절마다 고정한다(줄 끝 공백은 무시, 같은 제목은 ' #2'를 붙인다)."""
    import hashlib, re
    out = {}
    for path in johu_files():
        with open(path, encoding="utf-8") as f:
            lines = [l.rstrip() for l in f.read().splitlines()]
        secs, title, buf = {}, "(머리)", []
        for l in lines + ["## (끝)"]:
            if re.match(r"^#{2,3} ", l):
                secs[title] = hashlib.sha256("\n".join(buf).encode("utf-8")).hexdigest()[:16]
                title, buf = l.lstrip("#").strip(), []
                k = 2
                while title in secs:
                    title = f"{l.lstrip('#').strip()} #{k}"
                    k += 1
            buf.append(l)
        out[os.path.basename(path)] = secs
    return out


if __name__ == "__main__":
    if "--johu" in sys.argv or "--quotes" in sys.argv:
        for path, data in [(QUOTES, johu_quotes()), (DOCS, johu_docs())]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
                f.write("\n")
        print(f"{QUOTES} — 120개월 인용 고정\n{DOCS} — 01~10번 본문 절 고정")
        sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
        import check_consistency as C
        C.check_johu()
        C.check_errata_pins()
        for n_ in C.notes:
            print(" · 확인 권장:", n_)
        for p_ in C.problems:
            print(" - 실패:", p_)
        print("git diff references/0*_gungbok_*.md references/10_gungbok_*.md 로 바뀐 줄을 원문과 대조할 것")
        sys.exit(1 if C.problems else 0)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(build(), f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{OUT} — {len(CASES)}명조 + 시각 모름 {len(UNKNOWN_CASES)}")
