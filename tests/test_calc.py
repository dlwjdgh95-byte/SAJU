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


def test_daewoon_age_display_matches_start_age():
    d = json.loads(run_cli("--birth", "2023-08-12 15:23", "--gender", "M", "--json"))["대운"]
    assert d["start_age"] == 1 and d["age_exact"] == 1.49 and "만 1년 5개월" in d["나이 기준"]


def test_cli_warnings():
    d = json.loads(run_cli("--birth", "1960-06-15 12:00", "--gender", "M", "--json"))
    w = " ".join(d["경고"])
    assert "서머타임" in w and "UTC+8:30" in w
    d = json.loads(run_cli("--birth", "2026-02-04 05:03", "--gender", "M", "--json"))
    assert any("2분 이내" in x for x in d["경고"])


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
                       (["--birth", "2060-01-01 12:00", "--gender", "M", "--lunar"], "변환표 범위")]:
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
