#!/usr/bin/env python3
"""
build_fixtures.py — 교차검증 명조 픽스처(tests/fixtures/natal_cases.json)를 saju_calc.py로 다시 만든다.
24번 원전 명조 86命의 격 후보도 함께 넣는다(웹 엔진 격 규칙 검사용).

Python 테스트(test_calc.py)는 현재 계산이 이 파일과 같은지, Node 테스트(web_parity.test.mjs)는
웹 엔진이 이 파일과 같은지 본다. 계산 규칙을 일부러 바꿨을 때만 다시 만들고, 바뀐 줄을 리뷰한다.

  python3 tests/build_fixtures.py
"""

import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import saju_calc as S  # noqa: E402

OUT = os.path.join(HERE, "fixtures", "natal_cases.json")

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
]


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
                    "list": [x["ganzhi"] for x in dw["list"][:9]]},
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
    return {"_note": "saju_calc.py 기본 옵션(Asia/Seoul·서울 경도·LMT·자시 정설) 기준. tests/build_fixtures.py로 생성",
            "cases": rows, "corpus": corpus()}


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(build(), f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{OUT} — {len(CASES)}명조")
