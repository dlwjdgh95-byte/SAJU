#!/usr/bin/env python3
"""
build_web_tables.py — web/unui-sigantable.html의 표 구획을 saju_calc.py에서 생성한다.

JS 엔진이 쓰는 표(장간·관계·신살·운성), 절기표, Asia/Seoul 시간대 이력을 한 구획에 넣는다.
표의 정본은 saju_calc.py이고, HTML 쪽 구획은 손으로 고치지 않는다.

  python3 scripts/build_web_tables.py          # HTML 구획 갱신
  python3 scripts/build_web_tables.py --check  # 구획이 최신인지 검사 (CI)

절기표: 1900 입춘 ~ 2046 소한. 값 = 1900-01-01 00:00(KST 눈금)부터의 밀리초(올림), 앞 값과의 차를 16진수로 잇는다.
올림인 까닭: 출생 시각은 분 단위라, 절입이 hh:mm:00.6이면 hh:mm 출생은 절입 '전'이다. 내림하면 JS만 '후'로 본다.
밀리초인 까닭: 절입 1초 차이는 대운 교체 시각에서 약 2분(×121.75)이 되어, 월 경계에서 교체 연월이 갈린다.
시간대: [벽시계 전환점(분), UTC 오프셋(분), 서머타임(분)]. 전환점은 zoneinfo fold=0 규칙
(전환 UTC 시각 + 전후 오프셋 중 큰 쪽)으로 계산해, 같은 벽시계 입력에서 Python과 같은 오프셋을 고른다.
"""

import json, math, os, sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import saju_calc as S  # noqa: E402

HTML = os.path.join(HERE, "..", "web", "unui-sigantable.html")
BEGIN = "/* ══ GENERATED:TABLES — scripts/build_web_tables.py가 saju_calc.py에서 생성. 손으로 고치지 말 것 ══ */"
END = "/* ══ END GENERATED:TABLES ══ */"
TERM_Y0, TERM_Y1 = 1900, 2046
K_EPOCH = datetime(1900, 1, 1)          # KST(UTC+9) 눈금 기준
SEOUL_LON = S.PLACES["서울"][0]


def terms_hex():
    out, prev = [], 0
    for y in range(TERM_Y0, TERM_Y1 + 1):
        for k in range(12):
            kst = S.jie_datetime_utc(y, k) + timedelta(hours=9)
            ms = math.ceil((kst - K_EPOCH) / timedelta(milliseconds=1))
            out.append(format(ms - prev, "x"))
            prev = ms
    return ",".join(out)


def seoul_tz():
    """Asia/Seoul 오프셋 전환 목록 (1900~2050)."""
    zi = S.ZoneInfo("Asia/Seoul")
    def info(utc):
        lt = utc.replace(tzinfo=timezone.utc).astimezone(zi)
        return lt.utcoffset().total_seconds() / 60, (lt.dst() or timedelta(0)).total_seconds() / 60
    t, end = datetime(1900, 1, 1), datetime(2050, 1, 1)
    cur = info(t)
    first = list(cur)
    rows = []
    step = timedelta(hours=6)
    while t < end:
        nt = t + step
        ni = info(nt)
        if ni != cur:
            lo, hi = 0, int(step.total_seconds())    # 초 단위로 좁힌다 (1908 LMT→KST 전환은 15:32:08 UTC)
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if info(t + timedelta(seconds=mid)) == cur: lo = mid
                else: hi = mid
            hi = t + timedelta(seconds=hi)
            utc_min = (hi - K_EPOCH).total_seconds() / 60        # UTC 눈금 분
            wall_point = utc_min + max(cur[0], ni[0])
            rows.append([round(wall_point, 6), ni[0], ni[1]])
            cur = ni
        t = nt
    return first, rows


def block():
    tables = S.export_tables()
    tables.pop("JANGGAN_SCHOOLS")
    first, tz = seoul_tz()
    lines = [
        BEGIN,
        "const T = " + json.dumps(tables, ensure_ascii=False, separators=(",", ":")) + ";",
        f"const SEOUL_LON = {SEOUL_LON};",
        f"const TZ_SEOUL0 = {json.dumps(first)};      // 1900년 이전~첫 전환: [UTC 오프셋(분), 서머타임(분)]",
        "const TZ_SEOUL = " + json.dumps(tz, separators=(",", ":")) + ";",
        f"const TERM_Y0 = {TERM_Y0};",
        f'const TERMS_HEX = "{terms_hex()}";',
        END,
    ]
    return "\n".join(lines)


def main():
    check = "--check" in sys.argv
    html = open(HTML, encoding="utf-8").read()
    if BEGIN not in html or END not in html:
        sys.exit("HTML에 GENERATED:TABLES 구획 표시가 없다")
    a, b = html.index(BEGIN), html.index(END) + len(END)
    new = html[:a] + block() + html[b:]
    if check:
        if new != html:
            sys.exit("web/unui-sigantable.html 표 구획이 saju_calc.py와 다르다 — python3 scripts/build_web_tables.py 실행")
        print("web 표 구획 최신")
        return
    if new != html:
        open(HTML, "w", encoding="utf-8").write(new)
        print("web 표 구획 갱신")
    else:
        print("변경 없음")


if __name__ == "__main__":
    main()
