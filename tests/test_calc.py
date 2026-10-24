"""saju_calc.py 회귀 테스트 — references/00_errata.md의 교정 항목마다 하나 이상.

  python3 -m pytest -q
"""

import io, json, os, re, sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)
import saju_calc as S  # noqa: E402
import build_fixtures as F  # noqa: E402


def natal(wall, **kw):
    zasi = kw.pop("zasi", "next")
    t = S.resolve_time(datetime.strptime(wall, "%Y-%m-%d %H:%M"), **kw)
    pillars, minfo = S.four_pillars(t["utc"], t["local"], zasi)
    return pillars, minfo, t


def load(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)


# ── 일주·시주 경계 ─────────────────────────────────────────────

def test_day_anchor():
    assert S.day_pillar(datetime(1900, 1, 1, 12)) == "甲戌"
    assert S.day_pillar(datetime(2000, 1, 1, 12)) == "戊午"


def test_on_the_hour_belongs_to_previous_branch():     # errata #6
    assert S.hour_pillar("甲", datetime(2000, 1, 1, 23, 0))[0][1] == "亥"
    assert S.hour_pillar("甲", datetime(2000, 1, 1, 23, 1))[0][1] == "子"
    assert S.hour_pillar("甲", datetime(2000, 1, 1, 7, 0))[0][1] == "卯"
    assert S.hour_pillar("甲", datetime(2000, 1, 1, 7, 1))[0][1] == "辰"
    assert S.day_pillar(datetime(2000, 1, 1, 23, 0)) == "戊午"      # 23:00 정각은 일주를 넘기지 않는다
    assert S.day_pillar(datetime(2000, 1, 1, 23, 1)) == "己未"


def test_yajasi_hour_stem_uses_next_day():              # errata #17
    p, _, _ = natal("2000-01-07 23:50", solar="none", zasi="same")
    assert p[2] == "甲子" and p[3] == "丙子"
    p, _, _ = natal("2000-01-07 23:50", solar="none", zasi="next")
    assert p[2] == "乙丑" and p[3] == "丙子"


def test_yajasi_midnight_stays_with_previous_day():     # errata #30
    # 야자시설: 23:01~00:00이 야자시 구간. 00:00 정각은 아직 전날 일주·익일 일간 시두법 子시다
    for wall, day in [("2000-01-07 23:59", "甲子"), ("2000-01-08 00:00", "甲子"), ("2000-01-08 00:01", "乙丑")]:
        p, _, _ = natal(wall, solar="none", zasi="same")
        assert (p[2], p[3]) == (day, "丙子"), wall


# ── 절입 비교는 출생 순간으로 ──────────────────────────────────

def test_jie_compare_uses_birth_instant():              # errata #18
    assert natal("2026-02-04 05:30")[0][0] == "丙午"    # 입춘 05:02 — 보정 시각(04:58)으로 비교하면 乙巳
    assert natal("2026-02-04 04:50")[0][0] == "乙巳"
    assert natal("2026-09-07 23:50")[0][1][1] == "酉"   # 백로 23:41
    assert natal("2026-09-07 23:40")[0][1][1] == "申"


def test_daewoon_counts_from_birth_instant():
    p, minfo, t = natal("2026-02-04 05:30")
    dw = S.daewoon(p, "F", t["utc"], minfo)
    assert dw["direction"] == "역행"
    assert dw["days_to_jie"] == pytest.approx((t["utc"] - minfo["prev_jie_utc"]).total_seconds() / 86400, abs=0.01)
    assert dw["days_to_jie"] < 0.03                      # 입춘 28분 후


# ── 대운 ──────────────────────────────────────────────────────

def test_daewoon_direction_uses_year_stem():            # errata #1
    base = datetime(2024, 2, 20)
    minfo = {"next_jie_utc": base + timedelta(days=30), "next_jie_name": "경칩",
             "prev_jie_utc": base - timedelta(days=10), "prev_jie_name": "입춘"}
    p = ["甲辰", "丙寅", "乙丑", "丙子"]                  # 연간 양 · 일간 음
    m, f = S.daewoon(p, "M", base, minfo), S.daewoon(p, "F", base, minfo)
    assert m["direction"] == "순행" and m["start_age"] == 10
    assert f["direction"] == "역행" and f["start_age"] == 3
    assert m["list"][0]["ganzhi"] == "丁卯" and f["list"][0]["ganzhi"] == "乙丑"


def test_round_half_up():                               # errata #7
    assert S._round_half_up(4.5) == 5
    assert S._round_half_up(3.49) == 3
    assert S._round_half_up(-2.09) == -2


# ── 시간대·보정 ───────────────────────────────────────────────

@pytest.mark.parametrize("wall,off,dst", [
    ("1905-03-01 12:00", 507 + 52 / 60, 0),     # 지방평균시
    ("1910-06-01 08:00", 510, 0),               # UTC+8:30
    ("1950-07-20 09:10", 600, 60),              # 서머타임
    ("1958-01-15 12:00", 510, 0),               # UTC+8:30
    ("1960-06-15 12:00", 570, 60),              # UTC+8:30 + 서머타임
    ("1988-07-01 10:00", 600, 60),
    ("2026-01-01 12:00", 540, 0),
])
def test_seoul_history(wall, off, dst):                 # errata #23
    t = S.resolve_time(datetime.strptime(wall, "%Y-%m-%d %H:%M"))
    assert t["offset_min"] == pytest.approx(off)
    assert t["dst_min"] == dst


def test_ambiguous_wall_time_flagged():
    t = S.resolve_time(datetime(1987, 10, 11, 2, 30))
    assert t["ambiguous"] and t["dst_min"] == 60        # fold=0 → 서머타임 쪽


def test_longitude_and_eot():
    t = S.resolve_time(datetime(2026, 1, 1, 12, 0))
    assert t["corr_min"] == -32 and t["local"] == datetime(2026, 1, 1, 11, 28)
    assert S.resolve_time(datetime(1958, 1, 15, 12, 0))["corr_min"] == -2
    assert S.resolve_time(datetime(2026, 1, 1, 12, 0), solar="none")["corr_min"] == 0
    assert S.resolve_time(datetime(2026, 1, 1, 12, 0), longitude=S.PLACES["부산"][0])["corr_min"] == -24
    assert S.equation_of_time(datetime(2026, 11, 3, 3)) == pytest.approx(16.4, abs=0.3)
    assert S.equation_of_time(datetime(2026, 2, 11, 3)) == pytest.approx(-14.2, abs=0.3)
    lat = S.resolve_time(datetime(2026, 11, 3, 12, 0), solar="lat")
    assert lat["corr_min"] == S._round_half_up(lat["lon_corr_min"] + lat["eot_min"])


def test_fixed_offset_skips_history():
    t = S.resolve_time(datetime(1958, 1, 15, 12, 0), tz=9)
    assert t["offset_min"] == 540


# ── 절기 ──────────────────────────────────────────────────────

def test_apparent_longitude_of_date():                  # errata #14
    import ephem
    for y in (1950, 2000, 2026, 2045):
        e = ephem.next_solstice(f"{y}/6/1").datetime()
        assert abs((S.find_term_crossing(90, datetime(y, 6, 21)) - e).total_seconds()) < 2
        e = ephem.next_equinox(f"{y}/3/1").datetime()
        assert abs((S.find_term_crossing(0, datetime(y, 3, 20)) - e).total_seconds()) < 10


def test_jie_matches_kasi():                            # errata #22
    exact = 0
    terms = load("jie_golden.json")["terms"]
    for r in terms:
        got = S.jie_datetime_utc(r["year"], r["k"]) + timedelta(hours=9)
        want = datetime.strptime(r["kst"], "%Y-%m-%d %H:%M")
        shown = S.jie_display(got).replace(second=0, microsecond=0)      # 분 단위 반올림 표시
        assert abs((shown - want).total_seconds()) <= 60, r               # ±1분
        exact += shown == want
    assert len(terms) >= 51 and exact >= 47


# ── 음력 ──────────────────────────────────────────────────────

def test_lunar_input():
    pytest.importorskip("korean_lunar_calendar")
    assert S.lunar_to_solar(1995, 9, 6) == date(1995, 10, 29)
    assert S.lunar_to_solar(2023, 2, 1, leap=True) == date(2023, 3, 22)
    with pytest.raises(ValueError):
        S.lunar_to_solar(2024, 2, 1, leap=True)


# ── 장간·격 ───────────────────────────────────────────────────

def test_janggan_school_switch():                       # errata #19
    assert S.JANGGAN["子"] == "癸" and S.JANGGAN["辰"] == "乙癸戊"
    try:
        S.set_janggan_school("wolryul")
        assert S.JANGGAN["子"] == "壬癸" and S.JANGGAN["亥"] == "戊甲壬"
        assert all(S.BONGI[z] == S.JANGGAN[z][-1] for z in S.ZHI)
    finally:
        S.set_janggan_school("jangan_ga")
    assert S.JANGGAN == S.JANGGAN_SCHOOLS["jangan_ga"]


def test_gyeok_bongi_first():                           # errata #20
    c = S.gyeok_candidates(["甲子", "丙子", "戊午", "丙辰"])["후보"]
    assert c[0]["격"] == "정재격"                          # 子 본기 癸 — 천간 丙(편인)이 아니다
    c = S.gyeok_candidates(["甲寅", "丙寅", "甲子", "丙寅"])["후보"]
    assert c[0]["격"] == "건록격"
    c = S.gyeok_candidates(["己酉", "丙子", "壬寅", "丙午"])["후보"]
    assert c[0]["격"] == "양인격"
    c = S.gyeok_candidates(["甲子", "辛未", "辛酉", "壬辰"])["후보"]
    assert c[0]["격"] == "잡기 정재격(같은 오행 투간)"      # 「甲透未库」
    c = S.gyeok_candidates(["壬寅", "丁未", "丙寅", "壬辰"])["후보"]
    assert [x["격"] for x in c] == ["잡기 상관격(본기·미투출)", "잡기 비겁 투출(월겁 절차)"]
    # 같은 오행 투간은 고의 오행만 — 여기(丑 중 癸)와 같은 오행 壬, 본기 戊와 같은 土 己는 넣지 않는다 (errata #30)
    c = S.gyeok_candidates(["壬申", "癸丑", "己丑", "甲戌"])["후보"]
    assert [x["격"] for x in c] == ["잡기 편재격"]
    c = S.gyeok_candidates(["己未", "甲戌", "辛未", "癸巳"])["후보"]
    assert [x["격"] for x in c] == ["잡기 정인격(본기·미투출)"]
    c = S.gyeok_candidates(["己卯", "甲戌", "癸酉", "乙卯"])["후보"]
    assert c[0]["격"] == "잡기 정관격(본기·미투출)"


def test_gyeok_hoeguk_change():                         # errata #30 — 「丁生亥月…支全卯未，则化为印」
    c = S.gyeok_candidates(["癸卯", "癸亥", "丁未", "庚子"])["후보"]
    assert [x["격"] for x in c] == ["정관격", "인수격(회국 변화 후보)"]       # 「化为印」— 투간이 없으면 정·편을 가리지 않는다
    c = S.gyeok_candidates(["癸卯", "癸亥", "丁丑", "庚子"])["후보"]       # 未가 없으면 회국이 아니다
    assert [x["격"] for x in c] == ["정관격"]
    c = S.gyeok_candidates(["乙丑", "甲申", "丙辰", "戊子"])["후보"]       # 「丙生申月…干不透庚…或会子会辰…财化为煞」
    assert [x["격"] for x in c] == ["편재격", "식신격(변화 후보)", "관살격(회국 변화 후보)"]
    for ps, top in [(["庚子", "甲申", "丙辰", "己丑"], "편재격"),            # 본기 庚 투출 → 변하지 않는다
                    (["甲午", "丙寅", "癸卯", "甲戌"], "상관격"),            # 「丙生寅月，午戌会劫，而又或透甲…则仍为印」
                    (["甲寅", "丙寅", "辛卯", "庚寅"], "정재격")]:           # 「辛生寅月，透丙化官，而又透甲，格成正财」
        assert [x["격"] for x in S.gyeok_candidates(ps)["후보"]] == [top], ps


def test_gyeok_japgi_hoeji():                           # 35번 ③ 「如甲生辰月，逢申与子会局，则用水印」
    c = S.gyeok_candidates(["庚申", "庚辰", "甲子", "丙寅"])["후보"]
    assert [x["격"] for x in c] == ["잡기 인수격(회지 후보)", "잡기 편재격(본기·미투출)"]


CHAPTER = {"论正官": "정관", "论财": "재", "论印绶": "인수", "论食神": "식신", "论偏官": "칠살",
           "论伤官": "상관", "论阳刃": "양인", "论建禄月劫": "건록월겁"}


def _chapter_of(name):
    if name.startswith(("건록", "월겁")): return "건록월겁"
    if name.startswith("양인"): return "양인"
    for k, v in [("정관", "정관"), ("칠살", "칠살"), ("정재", "재"), ("편재", "재"), ("정인", "인수"),
                 ("편인", "인수"), ("식신", "식신"), ("상관", "상관")]:
        if k in name: return v
    return "?"


@pytest.mark.parametrize("school", ["jangan_ga", "wolryul"])
def test_corpus_top1_matches_chapter(school):          # errata #20 — 24번 원전 명조
    chap, total, hit, miss = None, 0, 0, []
    try:
        S.set_janggan_school(school)
        for l in open(os.path.join(ROOT, "references", "24_japyeong_cases.md"), encoding="utf-8"):
            m = re.match(r"^## .*〔(.+?)〕", l)
            if m:
                chap = CHAPTER.get(m.group(1)); continue
            m = re.match(r"^### (\S+)\. .*?〔(.+?)〕", l)
            if m and chap:
                top = S.gyeok_candidates(m.group(2).split())["후보"][0]["격"]
                total += 1
                if _chapter_of(top) == chap: hit += 1
                else: miss.append((m.group(1), top))
    finally:
        S.set_janggan_school("jangan_ga")
    assert total == 71 and hit == 71, miss


# ── 관계 ──────────────────────────────────────────────────────

def test_stem_relations():
    assert S.cheongan_relations("甲", "己") == ["천간합(土)"]
    assert S.cheongan_relations("甲", "庚") == ["천간충"]
    assert S.cheongan_relations("戊", "己") == []
    assert S.cheongan_relations("戊", "甲") == []
    r = S.stem_relations([("년간", "甲"), ("월간", "丙"), ("일간", "乙"), ("시간", "庚")])
    assert r["년간甲—시간庚"] == ["천간충", "격위(사이에 다른 천간이 있다)"]
    assert r["일간乙—시간庚"] == ["천간합(金)"]


def test_samhyeong_names():                             # errata #12
    assert S.SAMHYEONG["寅巳申"].startswith("무은지형")
    assert S.SAMHYEONG["丑戌未"].startswith("지세지형")
    assert frozenset("子卯") in S.HYEONG_PAIRS


def test_combo_up_to_14_chars():
    r = S.combo_report(["乙亥", "丙戌", "癸巳", "乙卯"], "대운:癸未,세운:丙午,월운:庚寅")
    done = {d["조합"]: d["성립"] for d in r["지지 3자 조합"]["완성"]}
    assert done == {"삼합 亥卯未(木국)": "운에서 완성", "삼합 寅午戌(火국)": "운에서 완성", "방합 巳午未(火)": "운에서 완성"}
    assert "년간乙—월운 천간庚" in r["천간 합충(운 개입분)"]


def test_combo_origin_only():
    r = S.combo_relations([("년지", "寅"), ("월지", "午"), ("일지", "戌"), ("시지", "子")])
    assert r["완성"][0]["성립"] == "원국 자체"
    r = S.combo_relations([("년지", "亥"), ("시지", "卯"), ("월운", "子")])
    assert r["대기(원국 2자)"] == ["삼합 亥卯未(木국): 원국 亥卯 — 未가 오면 완성"]
    # 원국이 이미 완성한 조합에 운이 같은 글자를 얹어도 '운에서 완성'이 아니다
    r = S.combo_relations([("년지", "寅"), ("월지", "午"), ("일지", "戌"), ("시지", "子"), ("대운", "甲午")])
    assert r["완성"][0]["성립"] == "원국 자체" and r["완성"][0]["구성"]["午"] == "월지·대운"
    assert S.relate_to_unse(["甲寅", "庚午", "丙戌", "戊子"], "甲午")["3자 조합 완성"] == ["없음"]


def test_combo_labels():
    p = ["甲寅", "庚午", "丙戌", "戊子"]
    assert S.combo_report(p, "癸未,세운:丙午,庚寅")["대상"].endswith("운1 癸未 / 세운 丙午 / 운2 庚寅")
    assert S.combo_report(p, "운1:癸未,丙午")["대상"].endswith("운1 癸未 / 운2 丙午")   # 자동 라벨은 준 라벨을 피한다
    for spec in ["년지:丁未", "월주:丁未", "세운:丙午,세운:丁未"]:
        with pytest.raises(ValueError):
            S.combo_report(p, spec)


# ── 인연 층위 土 역할 ─────────────────────────────────────────

def test_inyeon_earth_role():                           # errata #24
    p = ["乙亥", "丙戌", "癸巳", "乙卯"]
    g = S.inyeon_fit(p, ["水", "土"], "생금")
    assert g["辰"]["용신 방향"] == "◎" and g["戌"]["용신 방향"].startswith("△")
    j = S.inyeon_fit(p, ["水", "土"], "제수")
    assert j["戌"]["용신 방향"] == "◎" and j["丑"]["용신 방향"].startswith("△")
    n = S.inyeon_fit(p, ["水", "土"])
    assert n["未"]["용신 방향"].startswith("판정 보류")
    assert n["子"]["용신 방향"] == "◎" and n["午"]["용신 방향"] == "—"


# ── 픽스처 회귀 ───────────────────────────────────────────────

def test_fixtures_unchanged():
    fx = load("natal_cases.json")
    assert [(c["date"], c["time"], c["gender"]) for c in fx["cases"]] == [c[:3] for c in F.CASES]   # 케이스가 빠지면 실패
    for c in fx["cases"]:
        assert F.compute(c["date"], c["time"], c["gender"]) == c["expect"], (c["date"], c["time"], c["memo"])
    assert F.corpus() == fx["corpus"]
    assert F.injong_cases() == fx["injong"]
    assert [(c["date"], c["gender"]) for c in fx["unknown"]] == [c[:2] for c in F.UNKNOWN_CASES]
    for c in fx["unknown"]:
        assert F.compute_unknown(c["date"], c["gender"]) == c["expect"], (c["date"], c["memo"])


# ── 출력·CLI ──────────────────────────────────────────────────

def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        S.main(list(argv))
    return buf.getvalue()


def test_cli_birth_json():
    d = json.loads(run_cli("--birth", "1995-10-29 06:30", "--gender", "M", "--json"))
    assert d["pillars"] == ["乙亥", "丙戌", "癸巳", "乙卯"]
    assert d["대운"]["direction"] == "역행"
    assert "격 후보" in d and "천간 관계" in d and "지지 3자 조합" in d


def test_cli_lunar_and_place():
    pytest.importorskip("korean_lunar_calendar")
    d = json.loads(run_cli("--birth", "1995-09-06 06:30", "--lunar", "--gender", "M", "--place", "부산", "--json"))
    assert d["pillars"] == ["乙亥", "丙戌", "癸巳", "乙卯"]
    assert d["입력"]["시각 보정(분)"] == -24


def test_cli_lunar_day_missing_in_solar():
    pytest.importorskip("korean_lunar_calendar")
    d = json.loads(run_cli("--birth", "2023-02-30 12:00", "--lunar", "--gender", "M", "--json"))
    assert "양력 2023-03-21" in d["입력"]["입력 시각"]
    with pytest.raises(SystemExit):
        run_cli("--birth", "2023-02-30 12:00", "--gender", "M")


def test_cli_foreign_zone_needs_longitude():
    with pytest.raises(SystemExit):
        run_cli("--birth", "1990-06-15 12:00", "--gender", "M", "--zone", "America/New_York")
    with pytest.raises(SystemExit):
        run_cli("--birth", "1990-06-15 12:00", "--gender", "M", "--tz", "-4")
    with pytest.raises(SystemExit):                    # 보정량이 작아도 한국 밖 시간대면 경도를 요구한다
        run_cli("--birth", "1990-06-15 12:00", "--gender", "M", "--zone", "Asia/Tokyo")
    d = json.loads(run_cli("--birth", "1990-06-15 12:00", "--gender", "M", "--zone", "America/New_York",
                           "--longitude", "-74.006", "--json"))
    assert d["입력"]["시각 보정(분)"] == 4 and d["입력"]["출생지"].endswith("74.006°W")
    d = json.loads(run_cli("--birth", "1995-10-29 06:30", "--gender", "M", "--tz", "9", "--json"))
    assert d["pillars"] == ["乙亥", "丙戌", "癸巳", "乙卯"]


@pytest.mark.parametrize("argv", [
    ["--year-fortune", "2026", "--place", "뉴욕"],
    ["--birth", "1990-06-15 12:00", "--gender", "M", "--zone", "Asia/Nowhere"],
    ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--inyeon-scan", "2026-2030"],
    ["--birth", "1995-10-29 24:30", "--gender", "M"],
])
def test_cli_clean_errors(argv, capsys):
    with pytest.raises(SystemExit) as e:
        run_cli(*argv)
    assert isinstance(e.value.code, str)          # 메시지로 끝난다 (traceback 아님)


def test_cli_time_unknown():                              # errata #38 — 시주 없이 분석해야 웹과 같다
    d = json.loads(run_cli("--birth", "1980-02-07", "--gender", "M", "--json"))
    assert d["pillars"] == ["庚申", "戊寅", "庚戌"] and "시간" not in d["sipsin_gan"]
    assert [c["격"] for c in d["격 후보"]["후보"]] == ["편재격", "편인격(변화 후보)"]       # 12:00(壬午시)를 넣으면 寅午戌 회국이 생긴다
    assert any("23:33 이후 출생이면 辛亥일" in w for w in d["경고"])
    assert any(w.startswith("ℹ️ 시주 없이 3기둥으로 분석했다") and "오행 분포·통근·천간 관계·원국 지지 관계" in w
               for w in d["경고"])                                          # 날짜만 준 --birth도 3기둥 안내 (errata #41)
    d = json.loads(run_cli("--birth", "1955-09-08", "--gender", "M", "--json"))
    w = " ".join(d["경고"])
    assert "절입일 출생" in w and "00:00~00:02 출생이면 辛未일" in w and "23:00~23:59의 벽시계 시각이 두 번 있다" in w
    assert "전환 뒤 시계로 읽으면 23:03~23:59 출생은 癸酉일" in w          # 두 번째 23시대(UTC+8:30)는 익일 일주 — errata #40
    w = " ".join(json.loads(run_cli("--birth", "1948-06-01", "--gender", "M", "--json"))["경고"])
    assert "00:00~00:59의 벽시계 시각이 없다" in w and "전환 뒤 시계로 읽으면 00:00~00:32 출생은" in w
    w = " ".join(json.loads(run_cli("--birth", "1961-08-10", "--gender", "M", "--json"))["경고"])
    assert "00:00~00:29의 벽시계 시각이 없다" in w and "전환 뒤 시계로 읽어도 일주는 같다" in w
    # 자정을 넘는 시계 앞당김(1919-03-30 토론토 23:30 → 00:30)도 '없다'로 가린다
    w = " ".join(json.loads(run_cli("--birth", "1919-03-30", "--gender", "M", "--zone", "America/Toronto", "--longitude", "-79.38", "--json"))["경고"])
    assert "23:30~23:59의 벽시계 시각이 없다" in w
    w = " ".join(json.loads(run_cli("--birth", "1955-09-08 23:30", "--gender", "M", "--json"))["경고"])
    assert "이 벽시계 시각이 두 번 있다" in w and "전환 뒤 시계로 읽으면 乙未 乙酉 癸酉 壬子" in w
    w = " ".join(json.loads(run_cli("--birth", "1905-03-03", "--gender", "M", "--zasi", "same", "--json"))["경고"])
    assert "00:00 출생이면" in w and "00:00~00:00" not in w
    d = json.loads(run_cli("--birth", "1990-01-09", "--gender", "M", "--json"))
    assert d["tonggn"]["일간甲"] == ["연·월·일지에 뿌리 없음(시지 미상)"]
    p3 = json.loads(run_cli("--pillars", "庚申 戊寅 庚戌", "--relate", "丙午", "--inyeon", "--json"))
    assert p3["pillars"] == ["庚申", "戊寅", "庚戌"] and "시지" not in str(p3["신살"]["원국 지지 관계"]) and "시지" not in p3["운 대입"]["영역"]
    assert any(w.startswith("ℹ️ 시주 없이 3기둥으로 분석했다") for w in p3["경고"])
    assert "(시지 미상 — 일지 옆 시지와의 관계는 빠졌다)" in p3["배우자궁"]["간섭 강도"]
    # 시주에 따라 달라지는 판정은 3기둥이면 '시지 미상'을 붙인다 (errata #40·#41) — 4기둥에는 붙지 않는다
    q3 = json.loads(run_cli("--pillars", "己巳 丁丑 甲戌", "--injong", "丑", "--json"))
    assert q3["신살"]["개별 신살"]["양인(A)"] == ["연·월·일지에 없음(시지 미상)"]
    assert q3["신살"]["개별 신살"]["공망(A~B)"] == ["공망지 申酉", "연·월·일지에 해당 없음(시지 미상)"]
    assert q3["십성 인종"]["개폐 판정"]["시지 미상"] == "시지가 未(충)이면 충개고로 바뀐다"          # 합국 — 시지 충만 판정을 바꾼다
    q = json.loads(run_cli("--pillars", "己巳 丁丑 甲戌", "--injong", "辰", "--json"))["십성 인종"]["개폐 판정"]
    assert q["판정"].startswith("충개고") and "시지 미상" not in q                                   # 충개고는 시지와 상관없다 (errata #42)
    q = json.loads(run_cli("--pillars", "庚午 戊寅 甲午", "--injong", "辰", "--json"))["십성 인종"]["개폐 판정"]
    assert q["판정"].startswith("폐고") and q["시지 미상"] == "시지가 戌(충)이면 충개고, 申·子(삼합 짝)이면 합국으로 바뀐다"
    quad = q3["십성 인종"]["원국 교차(4분면)"]
    assert any("(연·월·일주 기준, 시주 미상)" in v and v.endswith(" (시주에 있으면 달라진다)") for v in quad.values())
    q4 = run_cli("--pillars", "己巳 丁丑 甲戌 丙寅", "--injong", "丑", "--inyeon", "--json")
    assert "시지 미상" not in q4 and "시주 미상" not in q4 and "3기둥" not in q4
    # --injong-year도 달마다 같은 규칙 — 합국 달(戊戌, 세운 午)은 시지 충만, 충개고 달은 표시하지 않는다 (errata #43)
    y = json.loads(run_cli("--pillars", "己巳 丁丑 甲戌", "--injong-year", "2026", "--json"))["연간 인종"]
    goji = {r["월"]: r["사고지"] for r in y["월운 12"] if "사고지" in r}
    assert goji["戊戌"]["개폐"].startswith("합국") and goji["戊戌"]["시지 미상"] == "시지가 辰(충)이면 충개고로 바뀐다"
    assert all("시지 미상" not in g for g in goji.values() if g["개폐"].startswith("충개고"))
    assert "'시지 미상' 항목" in y["⚠️ 개폐 판정 범위"]
    assert "시지 미상" not in run_cli("--pillars", "己巳 丁丑 甲戌 丙寅", "--injong-year", "2026", "--json")


@pytest.mark.parametrize("argv", [
    ["--birth", "1995-10-29 06:30", "--gender", "M", "--pillars", "甲子 丙寅 甲子 甲子"],
    ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--relate", "丙午", "--year-fortune", "2026"],
    ["--year-fortune", "2026", "--inyeon"],
    ["--pillars", "乙亥 丙戌"],
    ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--gender", "M"],                 # --pillars는 대운을 내지 않는다
    ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--zasi", "same"],
    ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--place", "부산"],               # --injong-year 없이
    ["--year-fortune", "2026", "--yongsin", "水"],
    ["--year-fortune", "2026", "--gender", "F", "--lunar"],
    ["--export-tables", "--birth", "1990-01-01 10:00"],
    ["--export-tables", "--janggan", "wolryul"],                       # 표 묶음은 학파와 상관없이 같다
    ["--export-tables", "--json"],
    ["--export-tables", "--birth", ""],
    ["--year-fortune", "2026", "--janggan", "wolryul"],
    ["--birth", "1990-06-15 12:50", "--gender", "M", "--zone", "Asia/Tokyo", "--tz", "9"],   # --tz 9여도 한국 밖 시간대면 경도가 필요하다
])
def test_cli_conflicting_modes(argv):                     # 한쪽 옵션을 말없이 버리지 않는다
    with pytest.raises(SystemExit) as e:
        run_cli(*argv)
    assert isinstance(e.value.code, str)


def test_daewoon_age_display_matches_start_age():
    d = json.loads(run_cli("--birth", "2023-08-12 15:23", "--gender", "M", "--json"))["대운"]
    assert d["start_age"] == 1 and d["age_exact"] == 1.49 and "만 1년 5개월" in d["나이 기준"] and "반올림한 관례 정수" in d["나이 기준"]
    d = json.loads(run_cli("--birth", "2026-02-04 05:30", "--gender", "F", "--json"))["대운"]     # 0으로 반올림되면 최소 1세 관례
    assert d["start_age"] == 1 and d["나이 기준"].startswith("대운수 1은 출생 후 경과 연수(만 0년 0개월)를 반올림하면 0이라 최소 1세 관례")


def test_daewoon_age_particle():                           # 대운수 N은/는 — 숫자 읽기(일·삼·육·칠·팔·십은, 이·사·오·구는)
    want = dict(zip(range(1, 11), "은는은는는은은은는은"))
    seen = set()
    for m in range(1, 13):
        for dd, g in [(1, "M"), (11, "F"), (21, "M")]:
            d = json.loads(run_cli("--birth", f"1990-{m:02d}-{dd:02d} 12:00", "--gender", g, "--json"))["대운"]
            seen.add(d["start_age"])
            assert d["나이 기준"].startswith(f"대운수 {d['start_age']}{want[d['start_age']]} "), d["나이 기준"]
    assert len(seen) >= 6, seen


def test_shared_outputs():                                  # web_parity.test.mjs '신살·원국 지지 관계·일간 뿌리'와 같은 명조·같은 값
    d = json.loads(run_cli("--birth", "1995-10-29 06:30", "--gender", "M", "--json"))
    assert d["신살"]["원국 지지 관계"] == {"년지亥—일지巳": ["충"], "년지亥—시지卯": ["반합(왕지 포함)"], "월지戌—일지巳": ["원진", "귀문"],
                                     "월지戌—시지卯": ["육합"], "일지巳—시지卯": ["격각"]}
    ind = d["신살"]["개별 신살"]
    assert ind["천을귀인(B)"][:2] == ["일지巳", "시지卯"] and ind["천라(C)"] == ["戌亥 동시 존재"] and ind["백호대살(B)"] == ["월주 丙戌"]
    assert ind["문창귀인(B)"] == ["卯 @ 시지"] and ind["학당귀인(B)"] == ["卯 @ 시지"] and d["tonggn"]["일간癸"] == ["년지亥(록왕)"]
    d = json.loads(run_cli("--birth", "1960-01-19 19:30", "--gender", "M", "--json"))
    assert d["pillars"] == ["己亥", "丁丑", "丙午", "戊戌"]
    assert d["신살"]["개별 신살"]["양인(A)"] == ["일지"] and d["신살"]["개별 신살"]["천을귀인(B)"][0] == "년지亥"
    assert d["신살"]["원국 지지 관계"]["월지丑—일지午"] == ["지지육해", "원진", "귀문"] and d["신살"]["원국 지지 관계"]["월지丑—시지戌"] == ["형"]
    assert d["tonggn"]["일간丙"] == ["일지午(록왕)", "시지戌(묘고)"]


def test_shinsal_individual_entries():                    # 금여·홍염·지망·괴강(시주·포함 견해)·고신·과숙·삼재(년지 기준) — web_parity '개별 신살'과 같은 명조
    d = json.loads(run_cli("--birth", "1977-07-07 08:30", "--gender", "M", "--json"))
    assert d["pillars"] == ["丁巳", "丙午", "乙丑", "庚辰"]
    ind = d["신살"]["개별 신살"]
    assert (ind["금여(C)"], ind["홍염살(C~D)"], ind["지망(C)"], ind["괴강(B)"], ind["고신·과숙(C)"]) == \
           (["巳 @ 년지"], ["午 @ 월지"], ["辰巳 동시 존재"], ["시주 庚辰"], ["과숙 辰"])
    assert d["신살"]["삼재(B~C)"] == "巳酉丑생 → 삼재 해당 년지: 亥子丑"
    d = json.loads(run_cli("--birth", "1980-11-14 20:30", "--gender", "F", "--json"))
    assert d["pillars"] == ["庚申", "丁亥", "辛卯", "戊戌"]
    ind = d["신살"]["개별 신살"]
    assert (ind["금여(C)"], ind["괴강(B)"], ind["고신·과숙(C)"], ind["천라(C)"]) == (["亥 @ 월지"], ["시주 戊戌(포함 견해)"], ["고신 亥"], ["戌亥 동시 존재"])
    assert d["신살"]["삼재(B~C)"] == "申子辰생 → 삼재 해당 년지: 寅卯辰"          # 일지 卯(亥卯未)가 아니라 년지 申 기준


def test_small_outputs():                                  # 이중 입묘·격위·학파 차이·윤달 안내 — 다른 테스트가 지나가지 않는 출력
    assert {g: [S.ijung_ipmyo(g, z) for z in "辰戌丑未"] for g in "甲丙庚"} == \
           {"甲": [[], ["편재"], ["정재"], []], "丙": [[], ["식신"], ["상관"], []], "庚": [[], ["편인"], ["정인"], []]}   # 墓이면서 그 지지 장간인 십성만
    assert S.stem_relations([("년간", "甲"), ("월간", "丙"), ("일간", "己")]) == {"년간甲—일간己": ["천간합(土)", "격위(사이에 다른 천간 — 합력 약화, 22 §1-3)"]}
    g = json.loads(run_cli("--pillars", "甲子 丁卯 丙寅 甲午", "--json"))["격 후보"]
    assert g["학파 차이"].startswith("월률분야 기준이면 卯 여기 甲(편인)도 투출로 본다")
    d = json.loads(run_cli("--birth", "2023-02-10 12:00", "--gender", "M", "--lunar", "--json"))
    assert "그해 2월은 윤달이 있다 — 윤2월 출생이면 --leap: 양력 2023-03-31" in d["입력"]["입력 시각"]


def test_quadrant_matches_doc():                           # 32번 §5-2 4분면 표 = saju_calc.QUADRANT
    sec = open(os.path.join(ROOT, "references/32_injong.md"), encoding="utf-8").read().split("### 5-2.")[1].split("\n\n```")[0]
    rows = [[c.strip().replace("**", "") for c in l.strip().strip("|").split("|")] for l in sec.splitlines() if l.startswith("| **")]
    got = {(r[0], st): cell for r in rows for st, cell in zip(("활", "전", "장"), r[1:])}
    assert got == S.QUADRANT


def test_gongmang_same_branch_twice():                     # 같은 공망 지지가 두 자리에 있으면 둘 다 (웹과 같다)
    d = json.loads(run_cli("--birth", "1971-06-15 23:10", "--gender", "F", "--json"))
    assert d["pillars"] == ["辛亥", "甲午", "辛未", "己亥"] and d["신살"]["개별 신살"]["공망(A~B)"] == ["공망지 戌亥", "년지亥", "시지亥"]


def test_cli_warnings():
    d = json.loads(run_cli("--birth", "1960-06-15 12:00", "--gender", "M", "--json"))
    w = " ".join(d["경고"])
    assert "서머타임" in w and "UTC+8:30" in w
    d = json.loads(run_cli("--birth", "2026-02-04 05:03", "--gender", "M", "--json"))
    assert any("2분 이내" in x and "연주·월주를 재확인" in x for x in d["경고"])          # 입춘은 연주·대운 순역까지 가른다
    for b, pz in [("2026-02-04 05:30", "연주·월주를 가른다"), ("2026-02-03 12:00", "연주·월주를 가른다"),
                  ("2026-03-05 12:00", "정확도가 월주를 가른다")]:
        w = " ".join(json.loads(run_cli("--birth", b, "--gender", "M", "--json"))["경고"])
        assert "±24시간 이내" in w and pz in w, (b, w)


def test_cli_korean_dst_offset_as_tz():                   # 한국 서머타임 기간의 --tz 10·9.5는 서머타임으로 받는다 (errata #43·#44)
    same = lambda d: (d["pillars"], d["입력"]["시각 보정(분)"], d["절기"]["월 구간"], d["대운"]["start_date"], d["대운"]["ref"],
                      [x["start"] for x in d["대운"]["list"]])
    for b, tz, g in [("1987-07-01 12:00", "10", "M"), ("1958-07-01 12:00", "9.5", "M"), ("1987-07-01 07:28", "10", "F"),
                     ("1987-05-16 12:35", "10", "F"), ("1958-06-30 12:37", "9.5", "M")]:   # 절입·대운 날짜도 그날의 한국 시계로 적는다
        auto = json.loads(run_cli("--birth", b, "--gender", g, "--json"))
        fixed = json.loads(run_cli("--birth", b, "--gender", g, "--tz", tz, "--json"))
        assert same(fixed) == same(auto), b
        assert fixed["입력"]["시간대"].startswith(f"UTC+{tz}(고정, 서머타임)")
        std = "9" if tz == "10" else "8.5"
        assert all(any(f"이미 표준시라면 --tz {std}로 다시 계산" in w for w in r["경고"]) for r in (auto, fixed))
        assert any("UTC+8:30" in w for w in auto["경고"]) == (tz == "9.5") and not any("UTC+8:30" in w for w in fixed["경고"])
    gap = " ".join(json.loads(run_cli("--birth", "1987-05-10 02:30", "--gender", "M", "--json"))["경고"])
    assert "전환 뒤 시계로 읽으면 丁卯 乙巳 己未 甲子" in gap
    d = json.loads(run_cli("--birth", "1987-05-10 02:30", "--gender", "M", "--tz", "10", "--json"))    # 경고가 알려 준 '전환 뒤' 값을 그대로 다시 낸다
    assert d["pillars"] == ["丁卯", "乙巳", "己未", "甲子"]


def test_cli_dst_offset_outside_korean_dst():              # 한국 서머타임 기간이 아니거나 경도가 한국 밖이면 --tz 10·9.5는 그 지역 표준시 (errata #44)
    with pytest.raises(SystemExit) as e:
        run_cli("--birth", "2000-07-01 14:00", "--gender", "M", "--tz", "10")
    assert "한국 밖 시간대(UTC+10)에는 출생지 경도가 필요하다" in str(e.value.code) and "서머타임 기간" in str(e.value.code)
    key = lambda d: (d["pillars"], d["입력"]["표준시"], d["입력"]["보정 후"], d.get("경고", []), d["대운"]["start_date"])
    for b, tz, lon, zone, extra, hour in [("2000-07-01 12:50", "10", "151.21", "Australia/Sydney", [], "壬午"),
                                          ("2000-07-01 14:00", "10", "151.21", "Australia/Sydney", [], "癸未"),
                                          ("2000-07-01 13:10", "9.5", "130.84", "Australia/Darwin", ["--no-solar-correction"], "癸未"),
                                          ("2000-07-01 13:10", "9.5", "130.84", "Australia/Darwin", [], "壬午"),
                                          ("1958-07-01 12:00", "9.5", "138.6", "Australia/Adelaide", [], "庚午")]:   # 1958 한국 서머타임 기간이지만 경도가 한국 밖
        fixed = json.loads(run_cli("--birth", b, "--gender", "M", "--tz", tz, "--longitude", lon, *extra, "--json"))
        auto = json.loads(run_cli("--birth", b, "--gender", "M", "--zone", zone, "--longitude", lon, *extra, "--json"))
        assert key(fixed) == key(auto) and fixed["pillars"][3] == hour, (b, zone)
        assert fixed["입력"]["시간대"] == f"UTC+{tz}(고정) " + auto["입력"]["시간대"].split(" ", 1)[1]


def test_dst_advice_particle():                            # 「--tz N으로/로」 — 영·삼·육·십은 으로 (errata #44)
    for b, zone, lon, want in [("2000-07-15 12:00", "Europe/London", "-0.12", "--tz 0으로"), ("2000-07-15 12:00", "Europe/Moscow", "37.62", "--tz 3으로"),
                               ("2000-01-15 12:00", "Australia/Sydney", "151.21", "--tz 10으로"), ("2000-01-15 12:00", "America/Sao_Paulo", "-46.63", "--tz -3으로"),
                               ("1987-07-01 12:00", "Asia/Seoul", "126.98", "--tz 9로")]:
        d = json.loads(run_cli("--birth", b, "--gender", "M", "--zone", zone, "--longitude", lon, "--json"))
        assert any(f"이미 표준시라면 {want} 다시 계산" in w for w in d["경고"]), (zone, d["경고"])


def test_cli_correction_boundary_warning():              # errata #30
    d = json.loads(run_cli("--birth", "2000-01-07 23:20", "--gender", "M", "--json"))
    assert d["pillars"][2:] == ["甲子", "乙亥"]
    assert any("乙丑일 丙子시" in w and "일주·시주가 갈린다" in w for w in d["경고"])
    d = json.loads(run_cli("--birth", "2000-01-07 12:00", "--gender", "M", "--json"))
    assert not any("경계 출생" in w for w in d.get("경고", []))


def test_cli_year_range():
    for argv in [["--birth", "1500-01-01 12:00", "--gender", "M"], ["--year-fortune", "2200"],
                 ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--injong-year", "1200"],
                 ["--pillars", "乙亥 丙戌 癸巳 乙卯", "--inyeon-scan", "2090:2110"]]:
        with pytest.raises(SystemExit) as e:
            run_cli(*argv)
        assert "년" in str(e.value.code), argv


def test_cli_numeric_ranges():
    b = ["--birth", "2000-01-01 12:00", "--gender", "M"]
    for argv, word in [(b + ["--tz", "99"], "--tz"), (b + ["--longitude", "nan"], "--longitude"),
                       (b + ["--longitude", "200"], "--longitude"),
                       (["--birth", "2060-01-01 12:00", "--gender", "M", "--lunar"], "변환표 범위"),
                       (b + ["--eot", "--no-solar-correction"], "함께 쓸 수 없다"),
                       (["--pillars", "乙亥 丙戌 癸巳 乙卯", "--combo", ""], "--combo"),
                       (["--pillars", "乙亥 丙戌 癸巳 乙卯", "--relate", ""], "--relate"),
                       (["--pillars", "乙亥 丙戌 癸巳 乙卯", "--injong", " "], "--injong"),
                       (["--pillars", "乙亥 丙戌 癸巳 乙卯", "--inyeon", "--yongsin", ""], "--yongsin"),
                       (["--pillars", "乙亥 丙戌 癸巳 乙卯", "--inyeon-scan", ""], "--inyeon-scan")]:
        with pytest.raises(SystemExit) as e:
            run_cli(*argv)
        assert word in str(e.value.code), argv


def test_cli_yongsin_options():
    ps = ["--pillars", "乙亥 丙戌 癸巳 乙卯"]
    d = json.loads(run_cli(*ps, "--inyeon", "--yongsin", "수,토", "--yongsin-role", "생금", "--json"))
    assert d["상대 지지 정합도"]["辰"]["용신 방향"] == "◎"
    for extra in [["--yongsin", "水,土"], ["--inyeon-activity"], ["--inyeon", "--yongsin", "물"],
                  ["--inyeon", "--yongsin", "水,火", "--yongsin-role", "생금"]]:
        with pytest.raises(SystemExit) as e:
            run_cli(*ps, *extra)
        assert isinstance(e.value.code, str), extra


def test_pillars_input_checked_against_month_and_hour_rules():
    assert S._pillars_warnings(["乙亥", "丙戌", "癸巳", "乙卯"]) == []
    assert S._pillars_warnings(["甲子", "丙寅", "甲子", "丙子"]) == []    # 야자시설 익일 일간 시두
    w = S._pillars_warnings(["乙亥", "戊戌", "癸巳", "丁卯"])
    assert len(w) == 2 and "월두법" in w[0] and "시두법" in w[1]
    d = json.loads(run_cli("--pillars", "乙亥 戊戌 癸巳 乙卯", "--json"))
    assert any("월두법" in x for x in d["경고"])


def test_cli_rejects_invalid_ganzhi():
    with pytest.raises(SystemExit):
        run_cli("--pillars", "戊未 丙戌 癸巳 乙卯")
    with pytest.raises(SystemExit):
        run_cli("--pillars", "乙亥 丙戌 癸巳 乙卯", "--relate", "甲丑")


def test_brief_drops_norms():
    assert S.brief({"⚠️ 규범": 1, "a": {"⚠️ x": 2, "b": [{"⚠️ y": 3, "c": 4}]}}) == {"a": {"b": [{"c": 4}]}}
    full = json.loads(run_cli("--pillars", "乙亥 丙戌 癸巳 乙卯", "--injong", "酉", "--json"))
    short = json.loads(run_cli("--pillars", "乙亥 丙戌 癸巳 乙卯", "--injong", "酉", "--brief", "--json"))
    assert len(json.dumps(short, ensure_ascii=False)) < len(json.dumps(full, ensure_ascii=False))
    assert "※" in short


def test_export_tables():
    t = json.loads(run_cli("--export-tables"))
    assert t["JANGGAN"] == S.JANGGAN_SCHOOLS["jangan_ga"]
    assert set(t["CHEONGAN_CHUNG"]) == {"甲庚", "乙辛", "丙壬", "丁癸"}
    assert t["YANGIN"] == S.YANGIN and t["ROK"]["戊"] == "巳"


# ── 궁통보감 json — 이미 고친 달이 옛 오류로 돌아가지 않도록 ───────────
@pytest.mark.parametrize("g,z,order,quote", [
    ("戊", "寅", "丙甲癸", "正二月先丙后甲，癸又次之"),       # errata #29 ①
    ("戊", "卯", "丙甲癸", "正二月先丙后甲，癸又次之"),
    ("壬", "亥", "戊丙庚", "十月壬水、专用戊丙，次取庚金"),     # #29 ②
    ("甲", "卯", "庚戊丙丁", "二月甲木，庚金得所"),            # #29 ③ — 正二月 공통 단락을 卯 단독처럼 자르지 않는다
    ("庚", "寅", "丙甲丁", "丙甲为上，丁火次之"),             # #32 ①
    ("癸", "寅", "辛丙庚", "先用辛金"),                       # #32 ②
    ("丁", "申", "甲庚丙", "七月丁火"),                       # #32 ③ — 三秋 공통 문장이 아니라 七月 단락
    ("丁", "酉", "甲庚丙", "三秋丁火，退气柔弱，耑用甲木"),
])
def test_johu_fixed_months(g, z, order, quote):
    with open(os.path.join(ROOT, "references", "johu_wonmun.json"), encoding="utf-8") as f:
        e = json.load(f)["table"][g][z]
    assert "".join(e["order"]) == order
    assert quote in e["quote"]


# 6차 검수(errata #38)에서 원문과 120개월을 모두 대조한 취용 순서 — 寅월부터 丑월까지.
# 원문이 순위 말을 두지 않은 글자 쌍(「庚辛壬参酌并用」 등)은 check_consistency가 원문에서 순서를 읽어 낼 수 없으므로, 여기서 고정한다.
# 바꾸려면 원문 근거와 함께 이 표·johu_wonmun.json·01~10번 문서·00_errata.md를 같이 고친다.
JOHU_PINNED = {
    "甲": "丙癸 庚戊丙丁 庚壬 癸丁庚 癸丁庚 丁庚 丁庚 丁丙庚 丁壬癸庚 庚丁丙戊 丁庚丙 庚丁",
    "乙": "丙癸 丙癸 癸丙 癸辛庚 癸丙 丙癸 丙己癸 癸丙丁 癸辛 丙戊 丙 丙",
    "丙": "壬庚 壬己 壬甲 壬庚癸 壬庚 壬庚 壬戊 壬癸 甲壬 甲戊庚壬 壬戊 壬甲",
    "丁": "庚甲 庚甲 甲庚 甲庚 壬庚癸 甲壬 甲庚丙 甲庚丙 甲庚 甲庚 甲庚 甲庚",
    "戊": "丙甲癸 丙甲癸 甲丙癸 甲丙癸 壬甲丙 癸丙甲 丙癸甲 丙癸 甲癸丙 甲丙 丙甲 丙甲",
    "己": "丙戊 甲癸丙 丙癸甲 癸丙 癸丙 癸丙 癸丙辛 癸丙辛 甲癸丙辛 丙甲戊 丙甲 丙甲",
    "庚": "丙甲丁 丁甲庚丙 甲丁 壬戊丙 壬癸 丁甲 丁甲 丁甲丙 甲壬 丁丙甲 丁甲丙 丙丁甲",
    "辛": "己壬庚 壬甲 壬甲 壬甲癸 己壬癸 壬庚 壬甲戊 壬甲 壬甲 壬丙 壬丙 丙壬戊己",
    "壬": "庚丙戊 戊辛庚 甲庚 壬辛庚癸 癸庚辛 辛甲癸 戊丁 甲庚 甲丙 戊丙庚 戊丙 丙丁甲",
    "癸": "辛丙庚 庚辛 丙辛甲 辛庚壬 庚辛壬癸 庚辛壬癸 丁甲 辛丙 辛甲壬癸 庚辛 丙辛 丙丁",
}


def test_johu_orders_pinned():
    with open(os.path.join(ROOT, "references", "johu_wonmun.json"), encoding="utf-8") as f:
        table = json.load(f)["table"]
    got = {g: " ".join("".join(table[g][z]["order"]) for z in S.MONTH_ZHI) for g in S.GAN}
    assert got == JOHU_PINNED


def test_johu_docs_pinned():
    """01~10번 본문을 절마다 고정한다 — 산문의 순서·순위·달 수 표기는 검사기가 다 읽지 못해 되돌림을 이 고정이 잡는다(errata #40).
    일부러 고쳤으면 python3 tests/build_fixtures.py --johu 로 다시 고정하고, 원문 근거를 errata에 적고, 바뀐 줄을 리뷰한다."""
    with open(F.DOCS, encoding="utf-8") as f:
        pinned = json.load(f)
    got = F.johu_docs()
    diff = [f"{name} {t}" for name in sorted(set(got) | set(pinned))
            for t in sorted(set(got.get(name, {})) | set(pinned.get(name, {})))
            if got.get(name, {}).get(t) != pinned.get(name, {}).get(t)]
    assert not diff, "고정 값과 다른 절(일부러 고쳤으면 --johu로 다시 고정): " + " / ".join(diff[:12])


def test_johu_quotes_pinned():
    """json 인용과 01~10번 '원문' 줄 인용을 고정한다 — 원문 문장을 빼거나 옛 인용으로 되돌리면 검사기가 못 잡는 경우가 있다(errata #39).
    인용을 일부러 바꿨으면 python3 tests/build_fixtures.py --johu 로 다시 고정하고 바뀐 줄을 리뷰한다."""
    with open(F.QUOTES, encoding="utf-8") as f:
        pinned = json.load(f)
    got = F.johu_quotes()
    diff = [f"{g}{z}" for g in S.GAN for z in S.MONTH_ZHI if got[g][z] != pinned[g][z]]
    assert not diff, f"인용이 고정 파일과 다른 달: {' '.join(diff)}"


def test_root_grade_earth():                               # 土는 화토동법 — 巳·午 록왕(건록격과 같다), 寅 장생 (errata #45)
    d = json.loads(run_cli("--pillars", "甲子 己巳 戊寅 壬子", "--json"))
    assert d["tonggn"]["일간戊"] == ["월지巳(록왕)", "일지寅(생지)"]
    assert d["격 후보"]["후보"][0]["격"].startswith("건록")
    assert json.loads(run_cli("--pillars", "甲子 庚午 己丑 甲子", "--json"))["tonggn"]["일간己"] == ["월지午(록왕)", "일지丑(록왕)"]


def test_place_zone_38th_parallel():                       # 개성·속초 — 1948~50년 남한 서머타임은 그때의 관할로 (errata #45)
    kae = json.loads(run_cli("--birth", "1949-07-01 10:10", "--place", "개성", "--gender", "M", "--json"))
    ref = json.loads(run_cli("--birth", "1949-07-01 10:10", "--longitude", "126.555", "--zone", "Asia/Seoul", "--gender", "M", "--json"))
    assert kae["pillars"] == ref["pillars"] and kae["입력"]["시간대"].startswith("KDT")
    sok = json.loads(run_cli("--birth", "1949-07-01 10:10", "--place", "속초", "--gender", "M", "--json"))
    assert sok["pillars"][3] == "乙巳" and not any("서머타임" in w for w in sok.get("경고", []))
    war = json.loads(run_cli("--birth", "1950-07-01 10:10", "--place", "개성", "--gender", "M", "--json"))
    assert any("개성은 6·25 전쟁 중 관할이 오간 곳" in w for w in war["경고"])
    for z, tzname in [("Asia/Seoul", "KDT"), ("Asia/Pyongyang", "KST")]:       # 경고가 권하는 재계산이 실제로 돈다
        re_ = json.loads(run_cli("--birth", "1950-07-01 10:10", "--place", "개성", "--zone", z, "--gender", "M", "--json"))
        assert re_["입력"]["시간대"].startswith(tzname) and not any("관할이 오간" in w for w in re_.get("경고", []))
    assert json.loads(run_cli("--birth", "1900-03-01 11:00", "--place", "개성", "--gender", "M", "--json"))["pillars"][3] == "戊午"   # 분할 전은 그대로
    assert not json.loads(run_cli("--birth", "1960-07-01 10:10", "--place", "개성", "--gender", "M", "--json")).get("경고")


def test_injong_year_tz_is_birth_only():                   # 출생 시각용 --tz(한국 오프셋)를 그해 월운 절입에 쓰지 않는다 (errata #45)
    def jie(*extra):
        d = json.loads(run_cli(*extra, "--gender", "M", "--injong-year", "2026", "--json"))
        return [r["절입"] for r in d["연간 인종"]["월운 12"]]
    auto = jie("--birth", "1987-07-15 10:00")
    assert auto[0] == "입춘 2026-02-04 05:02" and auto[7] == "백로 2026-09-07 23:41"
    for b, tz in [("1987-07-15 10:00", "10"), ("1957-07-01 10:00", "8.5"), ("1958-07-01 12:00", "9.5"), ("1970-07-01 12:00", "9")]:
        assert jie("--birth", b, "--tz", tz) == auto, (b, tz)
    sydney = json.loads(run_cli("--birth", "1987-07-15 10:00", "--gender", "M", "--tz", "10", "--longitude", "151.21", "--injong-year", "2026", "--json"))
    assert sydney["대운"]["start_date"] == "1989-12-26" and sydney["연간 인종"]["월운 12"][0]["절입"] == "입춘 2026-02-04 06:02"   # 한국 밖이면 그 고정 오프셋
    for b, tz, same_instant in [("1965-01-01 12:00", "8.5", "1965-01-01 12:30"), ("1958-01-15 12:00", "9", "1958-01-15 11:30")]:
        fixed = json.loads(run_cli("--birth", b, "--tz", tz, "--gender", "M", "--json"))["대운"]      # 대운 날짜도 그날의 한국 시계로
        auto = json.loads(run_cli("--birth", same_instant, "--gender", "M", "--json"))["대운"]
        assert (fixed["ref"], fixed["start_date"]) == (auto["ref"], auto["start_date"]), b


def test_inyeon_counts_by_doc():                            # 33번 §4-1·§5-4 — 세 가지를 하나씩, 격각·복음 제외, 활동은 식상 최고조 + 도화/일간 활 (errata #45)
    scan = lambda p, y, *x: json.loads(run_cli("--pillars", p, "--inyeon-scan", f"{y}:{y}", *x, "--json"))["인연 스캔"]["연도"][0]
    r = scan("庚午 辛巳 庚午 丙子", 2033)
    assert r["발동"] == "약" and r["신호"] == ["배우자궁 지지육해·원진·귀문"]
    assert scan("庚子 戊寅 庚子 丙子", 2032)["발동"] == "무"                    # 복음만
    assert scan("乙亥 丙戌 癸巳 乙卯", 2035)["발동"] == "무"                     # 격각만
    assert scan("甲子 丙寅 甲子 丙寅", 2033, "--inyeon-activity")["활동"]["활동"] == "중"   # 일간 관대(활)만
    assert scan("庚子 戊寅 庚子 丙子", 2030, "--inyeon-activity")["활동"]["활동"] == "약"   # 홍염만
    assert S.baeuja_gung([("甲","午"), ("甲","子"), ("甲","丑"), ("甲","子")])["간섭 강도"].startswith("부정 관계 2건")   # 丑午 해·원진·귀문 = 2


def test_johu_lookup_points_to_month_section():
    """조후 출력은 json 취용 순서와, 01~10번에서 그 달 절·요약 매트릭스만 읽을 줄 범위를 낸다 — 120개월 전부."""
    with open(os.path.join(ROOT, "references", "johu_wonmun.json"), encoding="utf-8") as f:
        table = json.load(f)["table"]
    for g in S.GAN:
        path = os.path.join(ROOT, "references", S.GUNGBOK_FILE[g])
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
        for z in S.MONTH_ZHI:
            j = S.johu_lookup(g, z)
            assert j["취용 순서"].split(" → ")[0].startswith(table[g][z]["order"][0])
            mon, mat = j["읽을 곳"]
            a, b = map(int, re.search(r"(\d+)~(\d+)줄", mon).groups())
            assert f"({z}月生)" in lines[a - 1] and lines[a - 1].startswith("###")
            assert not any(ln.startswith("#") and "月生" in ln for ln in lines[a:b])   # 다음 달로 넘치지 않는다
            a, _ = map(int, re.search(r"(\d+)~(\d+)줄", mat).groups())
            assert "조후 요약 매트릭스" in lines[a - 1]
