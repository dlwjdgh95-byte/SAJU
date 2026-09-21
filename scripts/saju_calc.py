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
    """태양의 겉보기(apparent) 지심 황경 — 그 시점(of-date) 좌표계 기준.

    ⚠️ errata #14: 과거에는 ephem.Ecliptic(s)를 그대로 썼는데, 이는 J2000 황경을 돌려준다.
    세차(약 50.3"/년) 때문에 2000년에서 멀어질수록 오차가 커져 절입 시각이
    2026년 약 +9시간, 2045년 약 +14시간, 1950년 약 -14시간까지 어긋났다.
    절기는 '겉보기 황경'(세차·장동·광행차 포함)으로 정의되므로 아래가 정본이다.
    검증: ephem.next_equinox/next_solstice 값과 1초 이내로 일치."""
    d = ephem.Date(dt_utc)
    s = ephem.Sun(d)
    eq = ephem.Equatorial(s.g_ra, s.g_dec, epoch=d)      # 겉보기 적도좌표(of-date)
    return math.degrees(ephem.Ecliptic(eq, epoch=d).lon) % 360

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
    res["신살"] = analyze_shinsal(pillars)
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

# ---------------- 신살·십이운성 (references/29, 30) ----------------

SAMHAP = {"申子辰":"水","亥卯未":"木","寅午戌":"火","巳酉丑":"金"}
SAMHAP_OF = {z: k for k in SAMHAP for z in k}
# 12신살 순서 (지지 순환 방향). 겁살 = 기준국 묘지 다음 지지
SINSAL12 = ["겁살","재살","천살","지살","년살","월살","망신살","장성살","반안살","역마살","육해살","화개살"]
_MYO = {"申子辰":"辰","亥卯未":"未","寅午戌":"戌","巳酉丑":"丑"}

def sibisinsal_table(gukja):
    """기준 삼합국 문자열 → {지지: 신살명}"""
    start = (ZHI.index(_MYO[gukja]) + 1) % 12      # 겁살 자리
    return {ZHI[(start + i) % 12]: SINSAL12[i] for i in range(12)}

def sibisinsal(base_zhi, target_zhi):
    """기준 지지(보통 년지)가 속한 삼합국 기준으로 target_zhi의 12신살."""
    return sibisinsal_table(SAMHAP_OF[base_zhi])[target_zhi]

# 십이운성 — 음포태(陰胞胎) 기준. 음간은 역행. (references/30 §2-2)
UNSEONG12 = ["장생","목욕","관대","건록","제왕","쇠","병","사","묘","절","태","양"]
_JANGSAENG = {"甲":"亥","乙":"午","丙":"寅","丁":"酉","戊":"寅",
              "己":"酉","庚":"巳","辛":"子","壬":"申","癸":"卯"}

def unseong(gan, zhi, mode="eum"):
    """일간(또는 임의 천간)이 지지에서 갖는 십이운성.
    mode='eum'  : 음포태 — 음간 역행 (서술·질감용, 본 저장소 기본 표기)
    mode='yang' : 양포태 — 음간도 같은 오행 양간과 동일 (통근·강약 계열)
    """
    if mode == "yang":
        g = {"乙":"甲","丁":"丙","己":"戊","辛":"庚","癸":"壬"}.get(gan, gan)
        step = 1
    else:
        g, step = gan, (-1 if YIN[gan] else 1)
    start = ZHI.index(_JANGSAENG[g])
    d = (ZHI.index(zhi) - start) * step % 12
    return UNSEONG12[d]

# 지지 관계
YUKHAP = {frozenset(p) for p in ["子丑","寅亥","卯戌","辰酉","巳申","午未"]}
CHUNG  = {frozenset(p) for p in ["子午","丑未","寅申","卯酉","辰戌","巳亥"]}
PA     = {frozenset(p) for p in ["子酉","丑辰","寅亥","卯午","巳申","未戌"]}
HAE    = {frozenset(p) for p in ["子未","丑午","寅巳","卯辰","申亥","酉戌"]}
WONJIN = {frozenset(p) for p in ["子未","丑午","寅酉","卯申","辰亥","巳戌"]}
GWIMUN = {frozenset(p) for p in ["子酉","丑午","寅未","卯申","辰亥","巳戌"]}
HYEONG_PAIRS = {frozenset(p) for p in ["寅巳","巳申","寅申",   # 寅巳申 = 무은지형
                                       "丑戌","戌未","丑未",   # 丑戌未 = 지세지형
                                       "子卯"]}                 # 子卯   = 무례지형 (누락 주의)
JAHYEONG = set("辰午酉亥")
BANGHAP = ["寅卯辰","巳午未","申酉戌","亥子丑"]

def zhi_relations(a, b):
    """두 지지 사이의 관계 전부. (references/22)"""
    r, pair = [], frozenset([a, b])
    if a == b:
        if a in JAHYEONG: r.append("자형")
        else: r.append("복음(같은 글자)")
        return r
    if pair in YUKHAP: r.append("육합")
    if pair in CHUNG:  r.append("충")
    if pair in HYEONG_PAIRS: r.append("형")
    if pair in PA:  r.append("파")
    if pair in HAE: r.append("지지육해")
    if pair in WONJIN: r.append("원진")
    if pair in GWIMUN: r.append("귀문")
    for guk in SAMHAP:
        if a in guk and b in guk:
            wang = guk[1]
            r.append("반합(왕지 포함)" if wang in (a, b) else "반합(왕지 미포함)")
            break
    for bh in BANGHAP:
        if a in bh and b in bh: r.append("방합 일부(2자)"); break
    if not r:
        d = (ZHI.index(a) - ZHI.index(b)) % 12
        if d in (2, 10): r.append("격각")
    return r

# 조견표 (일간 기준)
YANGIN     = {"甲":"卯","丙":"午","戊":"午","庚":"酉","壬":"子"}
MUNCHANG   = dict(zip(GAN, "巳午申酉申酉亥子寅卯"))
HAKDANG    = dict(_JANGSAENG)          # 학당귀인 = 일간의 장생지
GEUMYEO    = dict(zip(GAN, "辰巳未申未申戌亥丑寅"))
HONGYEOM   = dict(zip(GAN, "午午寅未辰辰戌酉子申"))
CHEONEUL   = {"甲":"丑未","戊":"丑未","庚":"丑未","乙":"子申","己":"子申",
              "丙":"亥酉","丁":"亥酉","壬":"巳卯","癸":"巳卯","辛":"午寅"}
BAEKHO     = {"甲辰","乙未","丙戌","丁丑","戊辰","壬戌","癸丑"}
GWAEGANG   = {"庚辰","庚戌","壬辰","壬戌"}
GWAEGANG_X = {"戊辰","戊戌"}          # 포함 견해
SAMJAE     = {"申子辰":"寅卯辰","亥卯未":"巳午未","寅午戌":"申酉戌","巳酉丑":"亥子丑"}
GOSIN_GWASUK = {"亥子丑":("寅","戌"),"寅卯辰":("巳","丑"),"巳午未":("申","辰"),"申酉戌":("亥","未")}

def gongmang(day_pillar_gz):
    """일주 기준 순중공망 2지지."""
    for i in range(60):
        if ganzhi(i) == day_pillar_gz:
            sun_start = i - (i % 10)          # 甲으로 시작하는 순의 첫 index
            return ZHI[(ZHI.index(ganzhi(sun_start)[1]) + 10) % 12] + \
                   ZHI[(ZHI.index(ganzhi(sun_start)[1]) + 11) % 12]
    return ""

def analyze_shinsal(pillars):
    """원국의 신살·십이운성 전개. references/29·30 규범에 맞춘 출력."""
    labels = ["년","월","일","시"]
    gans = [p[0] for p in pillars]
    zhis = [p[1] for p in pillars]
    day, yz, dz = gans[2], zhis[0], zhis[2]
    out = {}

    # 12신살 (년지 기준 + 일지 기준 병기)
    for base_lab, base in [("년지", yz), ("일지", dz)]:
        guk = SAMHAP_OF[base]
        out[f"12신살({base_lab} {base}·{guk}국)"] = {
            f"{labels[i]}지 {zhis[i]}": sibisinsal(base, zhis[i]) for i in range(4)}
    if SAMHAP_OF[yz] != SAMHAP_OF[dz]:
        out["12신살 기준 주의"] = "년지 기준과 일지 기준의 국이 달라 결과가 갈린다 — 병기 필수 (29_sibisinsal.md §1-1)"

    # 십이운성 (일간 기준, 두 방식 병기)
    out["십이운성(일간 기준)"] = {
        f"{labels[i]}지 {zhis[i]}": f"음포태 {unseong(day, zhis[i])} / 양포태 {unseong(day, zhis[i],'yang')}"
        for i in range(4)}
    # 십신 인종 (일간 제외 10천간)
    out["십신 인종(음포태)"] = {
        f"{labels[i]}지 {zhis[i]}": {sipsin(day, g): unseong(g, zhis[i]) for g in GAN}
        for i in range(4)}

    # 지지 상호 관계 (원국 내부)
    rel = {}
    for i in range(4):
        for j in range(i+1, 4):
            r = zhi_relations(zhis[i], zhis[j])
            if r: rel[f"{labels[i]}지{zhis[i]}—{labels[j]}지{zhis[j]}"] = r
    out["원국 지지 관계"] = rel or {"—": ["없음"]}

    # 개별 신살
    ind = {}
    ya = YANGIN.get(day)
    if ya: ind["양인(A)"] = [f"{labels[i]}지" for i in range(4) if zhis[i] == ya] or ["없음"]
    else:  ind["양인(A)"] = ["음간 — 양인 없음이 주류 견해"]
    for nm, tb, gr in [("문창귀인", MUNCHANG, "B"), ("학당귀인", HAKDANG, "B"),
                       ("금여", GEUMYEO, "C"), ("홍염살", HONGYEOM, "C~D")]:
        t = tb[day]
        hit = [f"{labels[i]}지" for i in range(4) if zhis[i] == t]
        if hit: ind[f"{nm}({gr})"] = [f"{t} @ " + "·".join(hit)]
    ch = CHEONEUL[day]
    hit = [f"{labels[i]}지{zhis[i]}" for i in range(4) if zhis[i] in ch]
    if hit: ind["천을귀인(B)"] = hit + ["※ 귀인은 결과가 아니라 통로"]
    gm = gongmang(pillars[2])
    hit = [f"{labels[i]}지{zhis[i]}" for i in range(4) if zhis[i] in gm]
    ind["공망(A~B)"] = [f"공망지 {gm}"] + (hit if hit else ["원국에 해당 없음"])
    bh = [f"{labels[i]}주 {pillars[i]}" for i in range(4) if pillars[i] in BAEKHO]
    if bh: ind["백호대살(B)"] = bh
    gg = [f"{labels[i]}주 {pillars[i]}" for i in range(4) if pillars[i] in GWAEGANG]
    gx = [f"{labels[i]}주 {pillars[i]}(포함 견해)" for i in range(4) if pillars[i] in GWAEGANG_X]
    if gg or gx: ind["괴강(B)"] = gg + gx
    tr = [z for z in zhis if z in "戌亥"]; jm = [z for z in zhis if z in "辰巳"]
    if len(set(tr)) == 2: ind["천라(C)"] = ["戌亥 동시 존재"]
    if len(set(jm)) == 2: ind["지망(C)"] = ["辰巳 동시 존재"]
    gs, gw = GOSIN_GWASUK[next(k for k in GOSIN_GWASUK if yz in k)]
    hit = [f"고신 {gs}" for z in zhis if z == gs] + [f"과숙 {gw}" for z in zhis if z == gw]
    if hit: ind["고신·과숙(C)"] = sorted(set(hit))
    out["개별 신살"] = ind
    out["삼재(B~C)"] = f"{SAMHAP_OF[yz]}생 → 삼재 해당 년지: {SAMJAE[SAMHAP_OF[yz]]}"
    out["⚠️ 사용 규범"] = ("신살은 격국·용신 판단의 보조다. 등급 C·D는 단독 서술 금지. "
                        "'지지육해'와 '12신살 육해살'은 다른 항목이다. (29·30번 참조)")
    return out

# ---------------- 십성 인종(引從) 체계 (references/32) ----------------
# 일간 → 십성 10개를 각각 천간으로 확정 → 대상 지지에서 음포태 운성을 읽는다.
# ⚠️ 서술 전용. 통근·강약 판정과 28번 점수식에는 절대 넣지 않는다. (32_injong.md §1)

SIPSEONG_ORDER = ["비견","겁재","식신","상관","편재","정재","편관","정관","편인","정인"]
SIPSEONG_GROUP = {"비견":"비겁","겁재":"비겁","식신":"식상","상관":"식상",
                  "편재":"재성","정재":"재성","편관":"관성","정관":"관성",
                  "편인":"인성","정인":"인성"}
GROUP_ORDER = ["비겁","식상","재성","관성","인성"]

# 12운성 3상태 — 수치 등급이 아니라 '작동 방식'의 분류 (32_injong.md §3)
UNSEONG_STATE = {
    "장생":"활","관대":"활","건록":"활","제왕":"활",   # 그대로 작동
    "목욕":"전","쇠":"전","병":"전","사":"전",         # 작동하되 성격이 바뀜
    "묘":"장","절":"장","태":"장","양":"장",           # 형체 없음·잠복
}
# 음포태에서 같은 오행 음양 한 쌍이 반드시 함께 떨어지는 슬롯 쌍 (32_injong.md §3-2)
SLOT_PAIR = {
    frozenset(("건록","제왕")): "최고조",
    frozenset(("장생","사")):   "갈림",
    frozenset(("목욕","병")):   "전환",
    frozenset(("태","절")):     "최저",
    frozenset(("관대","쇠")):   "관리",
    frozenset(("묘","양")):     "창고",
}
# 사고지(四庫) — 삼합의 묘고. 개폐 상태를 갖는 유일한 지지군 (32_injong.md §4)
GOJI_KEY   = {"辰":("申","子"), "戌":("寅","午"), "丑":("巳","酉"), "未":("亥","卯")}
GOJI_CHUNG = {"辰":"戌", "戌":"辰", "丑":"未", "未":"丑"}

def sipseong_gan(day_gan):
    """일간 → {십성: 천간}. 10천간과 10십성은 일대일 대응한다."""
    return {sipsin(day_gan, g): g for g in GAN}

def injong(day_gan, zhi):
    """일간 기준 십성 10개를 대상 지지에서 인종. {십성: 운성} (음포태)."""
    return {sipsin(day_gan, g): unseong(g, zhi) for g in GAN}

def injong_pairs(day_gan, zhi):
    """오행 그룹 5조로 묶은 인종 결과. 저자·실전 서술이 읽는 단위가 개별 십성이 아니라 이 5조다."""
    row = injong(day_gan, zhi)
    out = {}
    for grp in GROUP_ORDER:
        mem = [s for s in SIPSEONG_ORDER if SIPSEONG_GROUP[s] == grp]
        us = [row[s] for s in mem]
        out[grp] = {
            "십성": {s: row[s] for s in mem},
            "슬롯": SLOT_PAIR.get(frozenset(us), "혼합"),
            "상태": "".join(sorted({UNSEONG_STATE[u] for u in us})),
        }
    return out

def gaego(zhi, context):
    """사고지의 개폐(開閉) 판정. context = 대조할 지지 목록(원국 4자 + 세운·대운 지지 등).
    ⚠️ 개고 조건은 학파 이견 항목 — 충개고가 주류, 합은 작용 강화이지 개폐 조건이 아니다."""
    if zhi not in GOJI_KEY:
        return None
    ch = GOJI_CHUNG[zhi]
    keys = GOJI_KEY[zhi]
    hit_ch = [z for z in context if z == ch]
    hit_hap = [z for z in context if z in keys]
    out = {"묘고": zhi, "삼합 짝": "·".join(keys), "충 파트너": ch}
    if hit_ch:
        out["판정"] = "충개고(沖開庫) — 창고 문이 강제로 열린다"
        out["근거"] = f"대조 지지에 {ch} 존재 ({zhi}{ch}충)"
        out["주의"] = "개방과 동시에 손상을 동반한다. 열린 것이 곧 길한 것은 아니다"
    elif hit_hap:
        out["판정"] = "합국 성립 — 화개(華蓋) 작용 강화"
        out["근거"] = f"대조 지지에 {'·'.join(sorted(set(hit_hap)))} 존재 (반합)"
        out["주의"] = ("⚠️ 삼합 짝은 '작용 강화' 조건이지 개폐 조건이 아니다. "
                      "합이 묘고를 여는가 오히려 묶는가는 학파 이견 — 병기할 것")
    else:
        out["판정"] = "폐고(閉庫) — 잠복 유지"
        out["근거"] = "대조 지지에 충 파트너도 삼합 짝도 없음"
        out["주의"] = "입묘한 십성은 이 기간에 기대 영역이 아니다. 정리·보관 쪽으로 읽는다"
    return out

def ijung_ipmyo(day_gan, zhi):
    """이중 입묘(二重入墓) — 인종상 墓이면서 그 지지의 지장간이기도 한 십성.
    戌·丑에서만 성립한다(본기 戊·己가 각각 그 자리의 墓). 辰·未는 본기가 관대라 해당 없음."""
    if zhi not in GOJI_KEY:
        return []
    myo = {sipsin(day_gan, g) for g in GAN if unseong(g, zhi) == "묘"}
    jang = {sipsin(day_gan, g) for g in JANGGAN[zhi]}
    return sorted(myo & jang)

def wongug_hold(pillars, day_gan):
    """원국 보유도 — 각 십성의 천간이 원국에 실제로 있는가. (32_injong.md §5)
    투간 > 지장간 > 무. 일간 자신은 비견 판정에서 제외한다."""
    gans = [p[0] for p in pillars]
    other_gans = [g for i, g in enumerate(gans) if i != 2]
    jang = [c for p in pillars for c in JANGGAN[p[1]]]
    out = {}
    for s, g in sipseong_gan(day_gan).items():
        if g in other_gans:  out[s] = "투간"
        elif g in jang:      out[s] = "지장간"
        else:                out[s] = "무"
    return out

# 4분면 — 원국 보유도 × 인종 상태 (32_injong.md §5-2)
QUADRANT = {
    ("투간","활"):   "실질 발현 — 그대로 서술",
    ("투간","전"):   "기능 전환 — 있는데 쓰임새가 바뀐다",
    ("투간","장"):   "공회전 — 가지고 있으나 이 기간엔 굴러가지 않는다",
    ("지장간","활"): "점화 대기 — 운이 열어주는 영역",
    ("지장간","전"): "부분 작동 — 조건부로만",
    ("지장간","장"): "무효 — 서술하지 않는다",
    ("무","활"):     "⚠️ 허상 — 기회처럼 보이나 무근·고립일 수 있다 (errata #11)",
    ("무","전"):     "무효 — 서술하지 않는다",
    ("무","장"):     "무효 — 서술하지 않는다",
}

def injong_year(pillars, year, tz_hours=9):
    """세운 + 월운 12달을 인종으로 일괄 전개. 한 해의 '어느 십성이 언제 켜지는가' 시간표."""
    day = pillars[2][0]
    zhis = [p[1] for p in pillars]
    sy = sewoon(year)
    rows = []
    for r in wolwoon_table(year, tz_hours):
        z = r["month_zhi"]
        pr = injong_pairs(day, z)
        top = [g for g in GROUP_ORDER if pr[g]["슬롯"] == "최고조"]
        bot = [g for g in GROUP_ORDER if pr[g]["슬롯"] == "최저"]
        split = [g for g in GROUP_ORDER if pr[g]["슬롯"] == "갈림"]
        row = {"월": r["ganzhi"], "절입": f'{r["jie"]} {r["jie_enter"]}',
               "일간 운성": unseong(day, z),
               "최고조": top or ["—"], "최저": bot or ["—"], "갈림": split or ["—"],
               "세운 지지와의 관계": zhi_relations(sy[1], z) or ["없음"]}
        if z in GOJI_KEY:
            g = gaego(z, [sy[1]] + zhis)
            ii = ijung_ipmyo(day, z)
            row["사고지"] = {"개폐": g["판정"], "근거": g["근거"],
                           "이중 입묘": "·".join(ii) if ii else "없음(전환·관리 국면)"}
        rows.append(row)
    return {
        "세운": f"{year}년 {sy} (입춘 기준)",
        "세운 인종": injong_report(day, sy[1], pillars=pillars, context=[sy[1]], label="세운"),
        "월운 12": rows,
        "⚠️": ("층위 비중은 세운 12 > 월운 5 (28_scoring.md §1). 월운 인종은 발현 시점 참고이지 "
              "사건 예언이 아니다. 사고지 4달은 강약이 아니라 개폐로 읽는다"),
        "⚠️ 개폐 판정 범위": ("이 표의 사고지 개폐는 **세운 지지 + 원국 4지**만 대조한다. "
                         "대운 지지는 포함되지 않으므로, 대운까지 반영하려면 "
                         "injong_report(day, zhi, pillars, context=[세운지지, 대운지지])로 직접 호출한다"),
    }

def injong_report(day_gan, zhi, pillars=None, context=None, label="운"):
    """인종 전개 1회분. pillars를 주면 원국 교차(4분면)까지 얹는다."""
    row = injong(day_gan, zhi)
    kind = "왕지" if zhi in "子午卯酉" else ("생지" if zhi in "寅申巳亥" else "사고지")
    out = {
        "대상": f"{label} 지지 {zhi} ({kind})",
        "기준": "음포태(陰胞胎) 인종 — 서술 전용. 통근·강약·점수에는 쓰지 않는다",
        "일간 운성": f"{day_gan} → {unseong(day_gan, zhi)}",
        "십성 인종": {s: row[s] for s in SIPSEONG_ORDER},
        "오행 5조": injong_pairs(day_gan, zhi),
    }
    if kind == "사고지":
        ctx = list(context or [])
        if pillars: ctx += [p[1] for p in pillars]
        out["개폐 판정"] = gaego(zhi, ctx) if ctx else {"판정": "대조 지지 미입력 — 판정 불가"}
        ii = ijung_ipmyo(day_gan, zhi)
        out["이중 입묘"] = (f"{'·'.join(ii)} — 인종상 墓이면서 {zhi} 지장간. 이 달 개폐 판정의 주체"
                        if ii else f"{zhi}는 본기가 墓가 아니다(관대) — 이중 입묘 없음. 창고보다 전환·관리 국면")
        out["⚠️ 사고지 독법"] = ("사고지는 활(活)이 적은 대신 개폐 상태를 갖는 유일한 지지군이다. "
                            "'약한 달'이 아니라 '여닫는 달'로 읽는다")
    if pillars:
        hold = wongug_hold(pillars, day_gan)
        out["원국 교차(4분면)"] = {
            s: f"{row[s]}({UNSEONG_STATE[row[s]]}) · 원국 {hold[s]} → {QUADRANT[(hold[s], UNSEONG_STATE[row[s]])]}"
            for s in SIPSEONG_ORDER}
    out["⚠️ 출력 규범"] = ("십성 10개를 나열하지 않는다. 오행 5조로 묶어 최고조 1조·최저 1조·갈림 조를 말하고, "
                        "4분면에서 '무효'로 떨어진 십성은 서술에서 제외한다. (32_injong.md §6)")
    return out

def relate_to_unse(pillars, unse_gz, label="운"):
    """운(대운·세운·월운·일운) 간지 하나를 원국에 대입한 관계·신살 전개."""
    labels = ["년","월","일","시"]
    zhis = [p[1] for p in pillars]
    day, yz, dz = pillars[2][0], zhis[0], zhis[2]
    ug, uz = unse_gz[0], unse_gz[1]
    out = {"대상": f"{label} {unse_gz}", "천간 십신": f"{ug}({sipsin(day, ug)})",
           "지지 본기 십신": f"{uz}(본기 {BONGI[uz]}→{sipsin(day, BONGI[uz])})"}
    out["12신살"] = {
        f"년지 {yz} 기준": sibisinsal(yz, uz),
        f"일지 {dz} 기준": sibisinsal(dz, uz)}
    out["일간 십이운성"] = f"음포태 {unseong(day, uz)} / 양포태 {unseong(day, uz, 'yang')}"
    out["십성 인종"] = injong_report(day, uz, pillars=pillars, context=[uz], label=label)
    rel = {}
    for i in range(4):
        r = zhi_relations(zhis[i], uz)
        if r: rel[f"{labels[i]}지 {zhis[i]}"] = r
    out["원국과의 지지 관계"] = rel or {"—": ["직접 관계 없음"]}
    out["영역"] = "년지=총운 / 월지=직장·소속 / 일지=배우자·친밀 / 시지=자식·후배·결과물"
    gm = gongmang(pillars[2])
    if uz in gm: out["공망"] = f"{uz}는 일주 기준 공망지 — 학파 이견 병기 필요"
    return out


# ---------------- 인연 층위 (references/33) ----------------
# ⚠️ 저장소에서 근거가 가장 얇은 층위다. 축별 등급을 반드시 병기한다. (33_inyeon.md §1)
# ⚠️ 길흉 점수가 아니다. 28_scoring.md 점수 모델과 무관하며 어떤 축에도 합산하지 않는다.
# ⚠️ 사람을 판정·배제하는 용도로 쓰지 않는다. 상대 명조 없이 단정하지 않는다.

_NEG_REL = {"충","형","자형","파","지지육해","원진","귀문","격각","복음(같은 글자)"}
_POS_REL = {"육합","반합(왕지 포함)","반합(왕지 미포함)","방합 일부(2자)","삼합","방합"}
CHEONGAN_HAP = {frozenset(p) for p in [("甲","己"),("乙","庚"),("丙","辛"),("丁","壬"),("戊","癸")]}

def baeuja_gung(pillars):
    """배우자궁(일지) 구조. 등급 B — 궁위론."""
    labels = ["년","월","일","시"]
    zhis = [p[1] for p in pillars]
    day, dz = pillars[2][0], zhis[2]
    inner = {}
    for i in (0, 1, 3):
        r = zhi_relations(zhis[i], dz)
        if r: inner[f"{labels[i]}지 {zhis[i]}"] = r
    return {
        "배우자궁": f"일지 {dz} — 본기 {BONGI[dz]}({sipsin(day, BONGI[dz])})",
        "지장간": {c: sipsin(day, c) for c in JANGGAN[dz]},
        "원국 내 간섭": inner or {"—": ["없음"]},
        "간섭 강도": f"부정 관계 {sum(1 for v in inner.values() for r in v if r in _NEG_REL)}건",
        "⚠️": "배우자궁은 등급 B(궁위론)다. 재성=배우자 매핑은 고전의 전제이며 궁위·용신 축과 함께 읽는다",
    }

def inyeon_fit(pillars, yongsin_oheng=None):
    """상대 지지 후보 12개의 정합도. yongsin_oheng은 격국·조후로 **먼저 확정한** 실질 용신 오행 리스트.
    ⚠️ 스크립트는 용신을 판정하지 않는다. 판정은 SKILL.md Step 3-5~7에서 하고 그 결과를 넘긴다."""
    labels = ["년","월","일","시"]
    zhis = [p[1] for p in pillars]
    dz = zhis[2]
    ys = set(yongsin_oheng or [])
    out = {}
    for z in ZHI:
        rel = {}
        for i in range(4):
            r = zhi_relations(zhis[i], z)
            if r: rel[f"{labels[i]}지{zhis[i]}"] = r
        neg = sum(1 for v in rel.values() for r in v if r in _NEG_REL)
        pos = sum(1 for v in rel.values() for r in v if r in _POS_REL)
        ilji = zhi_relations(dz, z) or []
        oh = OHENG_Z[z]
        if not ys:                       yd = "미판정"
        elif oh == "土" and "土" in ys:   yd = "◎" if z in "辰丑" else "△ 조토 — 실질 무효"
        elif oh in ys:                   yd = "◎"
        else:                            yd = "—"
        row = {"오행": oh, "용신 방향": yd,
               "일지와": ilji or ["—"], "원국 관계": rel or {"—": ["없음"]},
               "긍정 관계": pos, "부정 관계": neg}
        if z in "辰丑":
            row["비고"] = "습토 — 金을 제대로 생한다 (25_byeongyak.md 조토불생금의 반대편)"
        elif z in "戌未":
            row["비고"] = "조토 — 이 위의 金은 통근처로 무효"
        out[z] = row
    out["⚠️ 읽는 법"] = ("지지 한 글자는 여덟 중 하나다. 이 표로 사람을 거르지 않는다. "
                     "상대의 격국·용신·대운이 한 글자를 얼마든지 뒤집는다")
    return out

def _inyeon_signals(day_gan, gz, zhis):
    """한 간지(세운·대운)의 인연 층위 신호 목록. 길흉이 아니라 '발동 여부'다."""
    g, z = gz[0], gz[1]
    dz = zhis[2]
    sig = []
    if frozenset((day_gan, g)) in CHEONGAN_HAP:
        sig.append(f"일간 천간합({day_gan}{g}합) — 일간이 직접 묶인다. 길흉은 화신·방어간으로 따로 판정")
    for r in (zhi_relations(dz, z) or []):
        if r in _POS_REL:   sig.append(f"배우자궁 {r}")
        elif r in _NEG_REL: sig.append(f"배우자궁 {r}")
    pr = injong_pairs(day_gan, z)
    if pr["재성"]["슬롯"] in ("최고조","갈림"):
        sig.append(f"재성 {pr['재성']['슬롯']}({'·'.join(pr['재성']['십성'].values())})")
    if sipsin(day_gan, g) in ("편재","정재"):
        sig.append(f"운 천간이 재성({sipsin(day_gan, g)})")
    return sig

def _inyeon_capacity(day_gan, z):
    """감당력(受容) — 들어온 것을 받을 수 있는 상태인가. 일간 운성 + 비겁·인성 조."""
    u = unseong(day_gan, z)
    st = UNSEONG_STATE[u]
    pr = injong_pairs(day_gan, z)
    bi, inn = pr["비겁"]["슬롯"], pr["인성"]["슬롯"]
    score = {"활": 2, "전": 0, "장": -2}[st] + {"최고조": 2, "관리": 1, "갈림": 1, "전환": 0, "창고": -1, "최저": -2}.get(bi, 0)
    lvl = "상" if score >= 3 else ("중" if score >= 0 else "하")
    return {"일간 운성": f"{u}({st})", "비겁조": bi, "인성조": inn, "감당력": lvl}

def _inyeon_activity(day_gan, z, year_zhi):
    """활동(活動) 축 — 친밀·활동 층위. (33_inyeon.md §5)
    ⚠️ 이 문서에서 등급이 가장 낮은 축이다. §4의 발동·수용과 합산하지 않는다.
    ⚠️ 빈도·성향·능력을 판정하지 않는다. 명리에 그 판정 근거가 없다."""
    pr = injong_pairs(day_gan, z)
    sik = pr["식상"]["슬롯"]
    u = unseong(day_gan, z)
    sig = []
    if sik == "최고조": sig.append(("A", f"식상 최고조({'·'.join(pr['식상']['십성'].values())}) — 욕구·표출 축"))
    elif sik == "갈림": sig.append(("A", "식상 갈림 — 음양이 나뉜다"))
    if z in "子午卯酉":
        nm = sibisinsal(year_zhi, z)
        if nm == "년살": sig.append(("B", f"진도화(년살) — 년지 {year_zhi} 삼합국 기준"))
        else:            sig.append(("A~B", f"왕지 도화({z}) — 12신살로는 {nm}"))
    if u == "목욕":
        sig.append(("A운성/C해석", "일간 목욕 — ⚠️ 정본표는 '씻고 꾸밈·치장·변덕(패지)'로 정의한다. "
                                  "성적 함의는 민간 확장이며 단독 근거로 쓰지 않는다 (33_inyeon.md §5-2)"))
    if z == HONGYEOM[day_gan]:
        sig.append(("C~D", "홍염 — ⚠️ 등급 C~D. 단독 문장으로 쓰지 않는다"))
    strong = any(gr.startswith("A") and "식상 최고조" in t for gr, t in sig)
    support = any("도화" in t for _, t in sig) or UNSEONG_STATE[u] == "활"
    lvl = "강" if (strong and support) else ("중" if sig else "약")
    return {"활동": lvl, "신호": [f"[{gr}] {t}" for gr, t in sig] or ["없음"],
            "⚠️": ("활동 강 ≠ 좋은 해가 아니다. 식상 최고조는 설기(洩氣)이기도 하다. "
                  "일간이 약하거나 재다신약인 명조에서는 소모가 커지는 구간일 수 있으므로 "
                  "수용 축과 **반드시 함께** 읽는다 (25_byeongyak.md ③)")}

def inyeon_scan(pillars, y0, y1, daewoon=None, activity=False):
    """연도별 인연 층위 스캔 — 발동(發動) × 수용(受容), 선택적으로 활동(活動).
    daewoon : 그 구간의 대운 간지(예: "癸未"). 주면 대운 층위 신호를 **별도로** 붙인다.
    activity: True면 친밀·활동 축(33_inyeon.md §5)을 **별도 축으로** 붙인다. 합산하지 않는다.
    ⚠️ 사건 예측이 아니라 압력의 방향 지도다. 축도 층위도 합치지 않는다."""
    day = pillars[2][0]
    zhis = [p[1] for p in pillars]
    rows = []
    for y in range(y0, y1 + 1):
        gz = sewoon(y)
        sig = _inyeon_signals(day, gz, zhis)
        cap = _inyeon_capacity(day, gz[1])
        rel = {}
        for i, lab in enumerate(["년","월","일","시"]):
            r = zhi_relations(zhis[i], gz[1])
            if r: rel[f"{lab}지{zhis[i]}"] = r
        pull = "강" if len(sig) >= 3 else ("중" if len(sig) == 2 else ("약" if sig else "무"))
        row = {"년": y, "세운": gz, "발동": pull, "신호": sig or ["없음"], "수용": cap, "원국 관계": rel or {"—": ["없음"]}}
        if activity: row["활동"] = _inyeon_activity(day, gz[1], zhis[0])
        rows.append(row)
    out = {}
    if daewoon:
        out["대운 층위"] = {
            "대운": daewoon,
            "신호": _inyeon_signals(day, daewoon, zhis) or ["없음"],
            "수용": _inyeon_capacity(day, daewoon[1]),
            "⚠️": ("대운은 세운보다 무겁다(28_scoring.md §1 — 대운 25 vs 세운 12). "
                  "세운 층위와 합산하지 말고, 대운을 배경으로 깔고 세운을 읽는다"),
        }
    out.update({
        "대상": f"{y0}~{y1} 세운 스캔 (입춘 기준)",
        "축": ("발동(發動) = 배우자궁·일간합·재성이 움직이는가 — **끌림의 질이 아니라 움직임의 크기다**. 충·형·원진도 발동으로 센다 / 수용(受容) = 그 움직임을 받을 일간 상태"),
        "연도": rows,
        "⚠️ 필수 고지": ("① 발동과 수용은 다른 축이다. 합산하지 않는다 "
                    "② 발동이 강한 해가 좋은 해라는 뜻이 아니다 — 자리가 크게 움직인다는 뜻이다. 충·형으로 움직이는 것도 발동이다 "
                    "③ 사건 예측이 아니라 압력의 방향이다. 누구를 언제 만나는지 이 표는 정하지 않는다 "
                    "④ 28_scoring.md 점수 모델과 무관하며 어떤 축에도 합산하지 않는다 "
                    "⑤ 대운 간지를 주지 않으면 이 표는 **세운 층위만** 본 것이다. "
                    "대운 천간이 일간과 합하는 구간은 10년 내내 그 신호가 깔리므로 반드시 함께 확인한다"),
        "⚠️ 활동 축": ("활동(活動)은 '맺어지는가'가 아니라 '그쪽 에너지가 활발한가'라는 별개 질문이다. "
                   "발동·수용과 합산하지 않는다. 이 문서에서 등급이 가장 낮은 축이며, "
                   "C~D 항목(홍염·음란지합)은 단독 문장으로 쓰지 않는다. "
                   "명리는 빈도·성향·능력을 판정하지 않는다 (33_inyeon.md §5-5)") if activity else None,
    })
    return out

def _inyeon_cli(a, ps):
    out = {}
    ys = [s.strip() for s in a.yongsin.split(",")] if a.yongsin else None
    if a.inyeon:
        out["배우자궁"] = baeuja_gung(ps)
        out["상대 지지 정합도"] = inyeon_fit(ps, ys)
    if a.inyeon_scan:
        y0, y1 = (int(x) for x in a.inyeon_scan.split(":"))
        out["인연 스캔"] = inyeon_scan(ps, y0, y1, a.inyeon_daewoon, a.inyeon_activity)
    return out

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
    ap.add_argument("--relate", metavar="干支",
                    help="운 간지 하나를 원국에 대입 (--pillars 또는 --birth와 함께). 예: --relate 丁酉")
    ap.add_argument("--injong", metavar="支",
                    help="십성 인종 전개. 지지 하나 또는 간지. --pillars/--birth와 함께 쓰면 원국 교차(4분면)까지. 예: --injong 酉")
    ap.add_argument("--injong-year", type=int, metavar="YYYY",
                    help="해당 연도 세운+월운 12달을 인종으로 일괄 전개 (--pillars 또는 --birth 필요)")
    ap.add_argument("--inyeon", action="store_true",
                    help="인연 층위 — 배우자궁 구조 + 상대 지지 후보 12개 정합도 (33_injong 규범 준수 필수)")
    ap.add_argument("--yongsin", metavar="오행",
                    help="실질 용신 오행. 쉼표 구분(예: 水,土). --inyeon의 용신 방향 판정에 쓴다. 격국·조후로 먼저 확정할 것")
    ap.add_argument("--inyeon-scan", metavar="Y0:Y1",
                    help="연도 구간의 인연 층위 2축 스캔(발동×수용). 예: --inyeon-scan 2026:2036")
    ap.add_argument("--inyeon-daewoon", metavar="干支",
                    help="--inyeon-scan에 대운 배경을 함께 표기. 예: --inyeon-daewoon 癸未")
    ap.add_argument("--inyeon-activity", action="store_true",
                    help="--inyeon-scan에 친밀·활동 축(도화·식상·목욕·홍염)을 별도 축으로 추가. 등급 낮음 — 33_inyeon.md §5 규범 준수 필수")
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
        if a.relate: res["운 대입"] = relate_to_unse(ps, a.relate)
        if a.injong: res["십성 인종"] = injong_report(ps[2][0], a.injong[-1], pillars=ps, context=[a.injong[-1]])
        if a.injong_year: res["연간 인종"] = injong_year(ps, a.injong_year, a.tz)
        res.update(_inyeon_cli(a, ps))
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
    if a.relate: res["운 대입"] = relate_to_unse(pillars, a.relate)
    if a.injong: res["십성 인종"] = injong_report(pillars[2][0], a.injong[-1], pillars=pillars, context=[a.injong[-1]])
    if a.injong_year: res["연간 인종"] = injong_year(pillars, a.injong_year, a.tz)
    res.update(_inyeon_cli(a, pillars))
    if warn: res["경고"] = warn
    # 절입 경계 ±1일 경고
    for edge, nm in [(minfo["prev_jie_local"], minfo["prev_jie_name"]),
                     (minfo["next_jie_local"], minfo["next_jie_name"])]:
        if abs((local-edge).total_seconds()) < 86400:
            res.setdefault("경고",[]).append(f"⚠️ 절입({nm}) ±24시간 이내 출생 — 월주 경계 재확인 권장")
    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
