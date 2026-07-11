#!/usr/bin/env python3
"""
saju_calc.py — 사주팔자 결정론적 계산 스크립트 (saju-expert skill)

사주 산출의 모든 결정론적 계산을 담당한다. SKILL.md의 지시에 따라
생년월일시 분석 요청 시 반드시 이 스크립트를 실행하고, 산문 규칙으로
암산하지 않는다.

기능:
  1. 사주팔자 산출 (절기 기반 월주, JDN 기반 일주, 진태양시 보정 옵션)
  2. 십신·장간·오행 분포·통근 분석 (등급: 록왕/생지/여기/묘고)
  3. 대운 (방향: 연간 음양 × 성별 [양남음녀 순행], 대운수: 절기까지 시간/3)
  4. 세운·월운 간지 산출 (절입 시각 포함)
  5. 사주 직접 입력 모드 (--pillars): 계산 없이 분석만

사용 예:
  python3 saju_calc.py --birth "1995-10-25 06:30" --gender M
  python3 saju_calc.py --birth "1995-10-25 06:30" --gender M --no-solar-correction
  python3 saju_calc.py --pillars "乙亥 丙戌 癸巳 乙卯"
  python3 saju_calc.py --year-fortune 2026          # 세운+월운 간지표
  python3 saju_calc.py --birth "..." --gender F --json

정확도 근거 (errata 참조):
  - 일주: 1900-01-01=甲戌 기준, 2000-01-01=戊午로 교차검증됨.
  - 대운 방향: 연간(年干) 기준 양남음녀 순행. (구 SKILL.md의 '일간 기준'은 오류 — errata #1)
  - 절기: ephem 라이브러리로 태양 황경 15°k 통과 시각을 이분탐색 (분 단위 정확도).
  - 진태양시: 한국 기본 보정 -32분 (서울 126.978°E vs 표준자오선 135°E).
    1948–1960·1987–1988 서머타임 해는 경고 출력.
"""

import argparse, json, sys, math
from datetime import datetime, timedelta

try:
    import ephem
except ImportError:
    ephem = None

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN_KO = dict(zip(GAN, "갑을병정무기경신임계"))
ZHI_KO = dict(zip(ZHI, "자축인묘진사오미신유술해"))
OHENG = dict(zip(GAN, ["木","木","火","火","土","土","金","金","水","水"]))
OHENG_Z = dict(zip(ZHI, ["水","土","木","木","土","火","火","土","金","金","土","水"]))
YIN = {g: (i % 2 == 1) for i, g in enumerate(GAN)}  # 乙丁己辛癸 = 음간
# 장간 — 정본 장간표(26_manual_calc.md §2-2)와 동일. 문자열 순서: 여기→중기→본기 (본기 = 마지막)
# ⚠️ 임의로 월률분야식 여기(卯의 甲, 酉의 庚, 午의 丙, 亥의 戊 등)를 추가하지 말 것 — 투출·통근 판정이 갈린다 (errata #8)
JANGGAN = {"子":"壬癸","丑":"辛癸己","寅":"戊丙甲","卯":"乙","辰":"癸乙戊","巳":"戊庚丙",
           "午":"己丁","未":"乙丁己","申":"戊壬庚","酉":"辛","戌":"丁辛戊","亥":"甲壬"}
BONGI = {z: JANGGAN[z][-1] for z in ZHI}
SHENG = {"木":"火","火":"土","土":"金","金":"水","水":"木"}
KE    = {"木":"土","土":"水","水":"火","火":"金","金":"木"}
# 십이운성 기반 통근 등급용: 각 천간 오행의 록/왕/생지
ROOT_GRADE = {  # 오행 → {지지: 등급}
    "木": {"寅":"록왕","卯":"록왕","亥":"생지","辰":"여기","未":"묘고"},
    "火": {"巳":"록왕","午":"록왕","寅":"생지","未":"여기","戌":"묘고"},
    "土": {"辰":"록왕","戌":"록왕","丑":"록왕","未":"록왕","巳":"생지","午":"생지"},
    "金": {"申":"록왕","酉":"록왕","巳":"생지","戌":"여기","丑":"묘고"},
    "水": {"亥":"록왕","子":"록왕","申":"생지","丑":"여기","辰":"묘고"},
}
# 월지 순서 (입춘 기준 절기월): 寅=0
MONTH_ZHI = "寅卯辰巳午未申酉戌亥子丑"
# 절(節) 경계: 입춘(315°)부터 30° 간격. index k → 月支 MONTH_ZHI[k]
JIE_NAMES = ["입춘","경칩","청명","입하","망종","소서","입추","백로","한로","입동","대설","소한"]

DAY_ANCHOR = datetime(1900, 1, 1)   # 甲戌일 = 60갑자 index 10 (2000-01-01=戊午 교차검증)
DAY_ANCHOR_IDX = 10

def ganzhi(idx):
    return GAN[idx % 10] + ZHI[idx % 12]

def sipsin(day_gan, other_gan):
    d, o = OHENG[day_gan], OHENG[other_gan]
    same = YIN[day_gan] == YIN[other_gan]
    if d == o:        return "비견" if same else "겁재"
    if SHENG[d] == o: return "식신" if same else "상관"
    if KE[d] == o:    return "편재" if same else "정재"
    if KE[o] == d:    return "편관" if same else "정관"
    if SHENG[o] == d: return "편인" if same else "정인"

# ---------------- 절기 (태양 황경) ----------------

def sun_lon(dt_utc):
    s = ephem.Sun(ephem.Date(dt_utc))
    return math.degrees(ephem.Ecliptic(s).lon) % 360

def find_term_crossing(target_deg, approx_utc, span_days=20):
    """target_deg 황경 통과 시각을 이분탐색 (UTC). approx 주변 ±span_days."""
    lo = approx_utc - timedelta(days=span_days)
    hi = approx_utc + timedelta(days=span_days)
    def diff(dt):
        d = (sun_lon(dt) - target_deg + 180) % 360 - 180
        return d
    # lo에서 음수, hi에서 양수가 되도록 보정
    if diff(lo) > 0: lo -= timedelta(days=20)
    if diff(hi) < 0: hi += timedelta(days=20)
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        if diff(mid) < 0: lo = mid
        else: hi = mid
    return lo

def jie_datetime_utc(year, k):
    """year년의 k번째 절(節) 절입 시각 UTC. k=0 입춘(2월)…k=11 소한(이듬해 1월)."""
    target = (315 + 30 * k) % 360
    approx_month = [2,3,4,5,6,7,8,9,10,11,12,1][k]
    approx_year = year if k < 11 else year + 1
    approx = datetime(approx_year, approx_month, 6)
    return find_term_crossing(target, approx)

def month_pillar_info(local_dt, tz_hours):
    """절기 기준 월지·해당 절기년(입춘 기준 연도)·전후 절입시각(로컬) 반환."""
    utc = local_dt - timedelta(hours=tz_hours)
    # 후보 절입들을 출생 전후로 수집
    terms = []  # (utc_dt, jie_year, k)
    for y in (utc.year - 1, utc.year, utc.year + 1):
        for k in range(12):
            terms.append((jie_datetime_utc(y, k), y, k))
    terms.sort(key=lambda t: t[0])
    prev = next_ = None
    for t in terms:
        if t[0] <= utc: prev = t
        else:
            next_ = t; break
    jie_year, k = prev[1], prev[2]
    month_zhi = MONTH_ZHI[k]
    return {
        "month_zhi": month_zhi, "jie_year": jie_year, "k": k,
        "prev_jie_local": prev[0] + timedelta(hours=tz_hours),
        "prev_jie_name": JIE_NAMES[k],
        "next_jie_local": next_[0] + timedelta(hours=tz_hours),
        "next_jie_name": JIE_NAMES[next_[2]],
    }

# ---------------- 기둥 산출 ----------------

def year_pillar(jie_year):
    """입춘 기준 연도의 연주."""
    return GAN[(jie_year - 4) % 10] + ZHI[(jie_year - 4) % 12]

def month_gan(year_gan, month_zhi):
    """월두법: 甲己→丙寅 시작, 乙庚→戊寅, 丙辛→庚寅, 丁壬→壬寅, 戊癸→甲寅."""
    start = {"甲":"丙","己":"丙","乙":"戊","庚":"戊","丙":"庚","辛":"庚",
             "丁":"壬","壬":"壬","戊":"甲","癸":"甲"}[year_gan]
    offset = MONTH_ZHI.index(month_zhi)
    return GAN[(GAN.index(start) + offset) % 10]

def day_pillar(local_dt, zasi_rule="late"):
    """일주. zasi_rule: 'late'=야자시(23시 이후를 당일 子시로, 일주는 익일로 넘기지 않음... 
    표준 처리) — 기본값 'next': 23:00 이후 출생은 익일 일주(자시 정설).
    여기서는 정설(자시=익일) 기준: 23:00 이상이면 날짜 +1."""
    d = local_dt
    # 정각 규칙과 일치: 23:00 정각은 亥시(이전 시지)이므로 일주를 넘기지 않는다.
    # 23:01부터 子시 → 익일 일주. (errata #6)
    if zasi_rule == "next" and (d.hour * 60 + d.minute) > 23 * 60:
        d = d + timedelta(days=1)
    days = (datetime(d.year, d.month, d.day) - DAY_ANCHOR).days
    return ganzhi((DAY_ANCHOR_IDX + days) % 60)

def hour_pillar(day_gan, local_dt):
    h, m = local_dt.hour, local_dt.minute
    # 경계 원칙: 정각(xx:00)은 이전 시지 (SKILL.md 1-4)
    minutes = h * 60 + m
    # 子 23:01~01:00 … 시지 인덱스: ((minutes - 1) 보정)
    adj = (minutes - 1) % 1440  # 정각을 이전 구간 끝으로
    zhi_idx = ((adj + 60) // 120) % 12  # 23:01부터 子(0)
    hz = ZHI[zhi_idx]
    start = {"甲":"甲","己":"甲","乙":"丙","庚":"丙","丙":"戊","辛":"戊",
             "丁":"庚","壬":"庚","戊":"壬","癸":"壬"}[day_gan]
    hg = GAN[(GAN.index(start) + zhi_idx) % 10]
    return hg + hz, zhi_idx

# ---------------- 분석 ----------------

def analyze_pillars(pillars):
    """4기둥 → 십신·장간·오행·통근 분석 dict."""
    yg, mg, dg, hg = [p[0] for p in pillars]
    yz, mz, dz, hz = [p[1] for p in pillars]
    day = dg
    res = {"pillars": pillars, "ilgan": day, "ilgan_oheng": OHENG[day],
           "ilgan_yinyang": "음간" if YIN[day] else "양간"}
    res["sipsin_gan"] = {
        "년간": f"{yg}({sipsin(day,yg)})", "월간": f"{mg}({sipsin(day,mg)})",
        "시간": f"{hg}({sipsin(day,hg)})"}
    res["sipsin_zhi_bongi"] = {
        lab: f"{z}(본기 {BONGI[z]}→{sipsin(day,BONGI[z])})"
        for lab, z in [("년지",yz),("월지",mz),("일지",dz),("시지",hz)]}
    res["janggan"] = {z: "·".join(f"{g}({sipsin(day,g)})" for g in JANGGAN[z])
                      for z in dict.fromkeys([yz,mz,dz,hz])}
    cnt = {}
    for g in [yg,mg,dg,hg]: cnt[OHENG[g]] = cnt.get(OHENG[g],0)+1
    for z in [yz,mz,dz,hz]: cnt[OHENG_Z[z]] = cnt.get(OHENG_Z[z],0)+1
    res["oheng_count"] = {o: cnt.get(o,0) for o in "木火土金水"}
    # 통근: 각 천간이 4지지 장간에 같은 오행을 갖는가 + 등급
    branches = [yz,mz,dz,hz]
    tonggn = {}
    for lab, g in [("년간",yg),("월간",mg),("일간",dg),("시간",hg)]:
        roots = []
        for pos, z in zip(["년지","월지","일지","시지"], branches):
            if any(OHENG[j]==OHENG[g] for j in JANGGAN[z]):
                grade = ROOT_GRADE[OHENG[g]].get(z, "장간")
                roots.append(f"{pos}{z}({grade})")
        tonggn[f"{lab}{g}"] = roots if roots else ["무근(無根)"]
    res["tonggn"] = tonggn
    # 월지 장간 투출 체크 (격국 1차 후보)
    transparent = [g for g in JANGGAN[mz] if g in (yg, mg, hg)]
    res["wolji_tuchul"] = ("·".join(f"{g}({sipsin(day,g)})" for g in transparent)
                          if transparent else f"미투출 → 본기 {BONGI[mz]}({sipsin(day,BONGI[mz])}) 기준")
    return res

def daewoon(pillars, gender, birth_local, month_info, tz_hours):
    """대운: 방향(연간 음양×성별), 대운수(절기까지 시간/3), 간지 10개."""
    year_gan = pillars[0][0]
    yang_year = not YIN[year_gan]
    forward = (yang_year and gender == "M") or ((not yang_year) and gender == "F")
    if forward:
        delta = month_info["next_jie_local"] - birth_local
        ref = f"다음 절기 {month_info['next_jie_name']}({month_info['next_jie_local']:%Y-%m-%d %H:%M})"
    else:
        delta = birth_local - month_info["prev_jie_local"]
        ref = f"이전 절기 {month_info['prev_jie_name']}({month_info['prev_jie_local']:%Y-%m-%d %H:%M})"
    days = delta.total_seconds() / 86400
    age_exact = days / 3            # 3일 = 1년
    # 전통 반올림(0.5 올림). 파이썬 round()는 banker's rounding이라 4.5→4가 되므로 사용 금지 (errata #7)
    start_age = math.floor(age_exact + 0.5)
    if start_age == 0: start_age = 1  # 최소 1세 관례
    mp = pillars[1]
    midx = (GAN.index(mp[0]) % 10, ZHI.index(mp[1]) % 12)
    # 월주의 60갑자 index
    for i in range(60):
        if ganzhi(i) == mp: m60 = i; break
    seq = []
    for n in range(1, 11):
        idx = (m60 + n) % 60 if forward else (m60 - n) % 60
        seq.append(ganzhi(idx))
    return {"direction": "순행" if forward else "역행",
            "rule": f"연간 {year_gan}({'양' if yang_year else '음'}간) × {'남' if gender=='M' else '여'}명 → {'순행' if forward else '역행'} (양남음녀 순행)",
            "ref": ref, "days_to_jie": round(days,2),
            "start_age": start_age, "age_exact": round(age_exact,2),
            "list": [{"n":i+1, "ganzhi":gz, "age":start_age+10*i} for i,gz in enumerate(seq)]}

def sewoon(year):
    return year_pillar(year)

def wolwoon_table(year, tz_hours=9):
    yg = year_pillar(year)[0]
    rows = []
    for k in range(12):
        jdt = jie_datetime_utc(year, k) + timedelta(hours=tz_hours)
        mzhi = MONTH_ZHI[k]
        rows.append({"month_zhi": mzhi, "ganzhi": month_gan(yg, mzhi)+mzhi,
                     "jie": JIE_NAMES[k], "jie_enter": jdt.strftime("%Y-%m-%d %H:%M")})
    return rows

# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--birth", help='출생 "YYYY-MM-DD HH:MM" (표준시)')
    ap.add_argument("--gender", choices=["M","F"], help="M 남명 / F 여명")
    ap.add_argument("--tz", type=float, default=9.0, help="표준시 UTC 오프셋 (기본 9=KST)")
    ap.add_argument("--longitude", type=float, default=126.978, help="출생지 경도 (기본 서울)")
    ap.add_argument("--no-solar-correction", action="store_true",
                    help="진태양시 보정 끄기 (기본: 경도 기반 보정 적용)")
    ap.add_argument("--zasi", choices=["next","same"], default="next",
                    help="자시 처리: next=23시 이후 익일 일주(정설, 기본), same=당일 유지(야자시설)")
    ap.add_argument("--pillars", help='사주 직접 입력 "乙亥 丙戌 癸巳 乙卯" (분석만)')
    ap.add_argument("--year-fortune", type=int, help="해당 연도 세운·월운 간지표만 출력")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.year_fortune:
        out = {"세운": f"{a.year_fortune}년 {sewoon(a.year_fortune)}",
               "월운": wolwoon_table(a.year_fortune, a.tz)}
        print(json.dumps(out, ensure_ascii=False, indent=2)); return

    if a.pillars:
        ps = a.pillars.split()
        assert len(ps)==4 and all(len(p)==2 and p[0] in GAN and p[1] in ZHI for p in ps), "사주 형식 오류"
        res = analyze_pillars(ps)
        print(json.dumps(res, ensure_ascii=False, indent=2)); return

    if not (a.birth and a.gender):
        ap.error("--birth와 --gender 필요 (또는 --pillars / --year-fortune)")
    if ephem is None:
        sys.exit("ephem 미설치: pip install ephem --break-system-packages")

    std_dt = datetime.strptime(a.birth, "%Y-%m-%d %H:%M")
    warn = []
    if std_dt.year in list(range(1948,1952))+list(range(1955,1961))+[1987,1988]:
        warn.append("⚠️ 서머타임 시행 가능 연도 — 출생시각이 서머타임 적용분(+1h)인지 확인 필요")
    if 1954 <= std_dt.year <= 1961:
        warn.append("⚠️ 1954-08~1961-08 한국 표준시는 UTC+8:30이었음 — 필요시 --tz 8.5")
    # 진태양시 보정
    if a.no_solar_correction:
        local = std_dt; corr = 0
    else:
        corr = (a.longitude - a.tz*15) * 4  # 분
        local = std_dt + timedelta(minutes=corr)
    minfo = month_pillar_info(local, a.tz)
    yp = year_pillar(minfo["jie_year"])
    mp = month_gan(yp[0], minfo["month_zhi"]) + minfo["month_zhi"]
    dp = day_pillar(local, zasi_rule=a.zasi)
    hp, _ = hour_pillar(dp[0], local)
    pillars = [yp, mp, dp, hp]
    res = analyze_pillars(pillars)
    res["입력"] = {"표준시": a.birth, "진태양시 보정(분)": round(corr,1),
                  "보정 후": local.strftime("%Y-%m-%d %H:%M"), "자시 규칙": a.zasi}
    res["절기"] = {"월 구간": f"{minfo['prev_jie_name']}({minfo['prev_jie_local']:%m-%d %H:%M}) ~ {minfo['next_jie_name']}({minfo['next_jie_local']:%m-%d %H:%M})"}
    res["대운"] = daewoon(pillars, a.gender, local, minfo, a.tz)
    if warn: res["경고"] = warn
    # 절입 경계 ±1일 경고
    for edge, nm in [(minfo["prev_jie_local"], minfo["prev_jie_name"]),
                     (minfo["next_jie_local"], minfo["next_jie_name"])]:
        if abs((local-edge).total_seconds()) < 86400:
            res.setdefault("경고",[]).append(f"⚠️ 절입({nm}) ±24시간 이내 출생 — 월주 경계 재확인 권장")
    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
