#!/usr/bin/env python3
"""
check_consistency.py — 문서와 코드가 같은 표를 쓰는지, 문서 구조가 깨지지 않았는지 검사한다.

  python3 scripts/check_consistency.py      # 문제가 있으면 목록을 출력하고 종료 코드 1

검사 항목
  1. 장간표: references/26 §2-2 ↔ saju_calc.JANGGAN (지장간가)
  2. 원전 코퍼스 주석: references/24의 '장간 …' 주석 ↔ saju_calc
  3. 십이운성 정본표: references/30 §2-2 ↔ saju_calc.unseong() (12행·10간 모두)
  4. 신살 조견표: references/30 §3-1·3-2 ↔ saju_calc 표 (행이 빠지거나 형식이 바뀌면 실패)
  5. 삼형 명칭: references/22·SKILL.md 정본 줄(子卯 포함)·22 §4-1 머리 ↔ saju_calc.SAMHYEONG·HYEONG_PAIRS
  6. 조후 용신
     - johu_wonmun.json 인용·취용 ↔ 窮通寶鑑 원문(tests/fixtures/qtbj_wikisource.txt): 인용은 그 달 단락이나 계절 머리말에, 취용 글자는 계절 단락에 있어야 한다
       인용은 1순위 글자를 담고 그 달 자리에서 시작해야 하며(달 숫자·첫머리 N月·바로 앞 달 표시), 인용 속 순위 말(先X后Y·Y次之·X为主)이 order와 맞아야 한다
     - references/01~10 월별 원문 줄(「」 전부, 취용 글자가 모두 근거로 나오는지)·취용 순서 줄·매트릭스(순서 포함)·본문 용신·희신(N순위)·기신 목록(십성 이름 포함) ↔ json
  7. 마크다운 표 깨짐 (빈 줄로 끊긴 표 등)
  8. SKILL.md·README·references/*.md가 가리키는 파일의 존재 (경로를 쓴 참조와 파일 이름만 쓴 참조 모두)
  9. 웹 엔진 표 구획이 최신인지 (scripts/build_web_tables.py --check와 같음)
"""

import glob, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import saju_calc as S  # noqa: E402

REF = os.path.join(ROOT, "references")
problems = []


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def section(text, start_pat, end_pat=r"^#{1,4} "):
    m = re.search(start_pat, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    e = re.search(end_pat, rest, re.M)
    return rest[: e.start()] if e else rest


def table_rows(text):
    return [[c.strip() for c in l.strip().strip("|").split("|")]
            for l in text.splitlines() if l.strip().startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", l.strip())]


# 1 ─ 장간표 26 §2-2
def check_janggan_doc():
    sec = section(read("references/26_manual_calc.md"), r"^### 2-2\.")
    rows = table_rows(sec)[1:]
    got = {}
    for z, bon, jung, yeo in rows:
        got[z] = "".join(c for c in (yeo, jung, bon) if c not in ("-", "—", ""))
    want = S.JANGGAN_SCHOOLS["jangan_ga"]
    if got != want:
        for z in S.ZHI:
            if got.get(z) != want[z]:
                problems.append(f"26 §2-2 장간표 {z}: 문서 {got.get(z)} ≠ 코드 {want[z]} (여기→중기→본기)")


# 2 ─ 24 코퍼스 주석
def check_corpus_notes():
    cur, cases, notes = None, 0, 0
    for i, l in enumerate(read("references/24_japyeong_cases.md").splitlines(), 1):
        m = re.match(r"^### .*〔(.+?)〕", l)
        if m:
            cur = m.group(1).split()
            cases += 1
            continue
        if l.startswith("- 일간 "):
            notes += 1
        m = re.match(r"^- 일간 \*\*(.)\*\* / 월지 \*\*(.)\*\* \(본기 (\S+?); 장간 (.+)\)$", l)
        if l.startswith("- 일간 ") and not m:
            problems.append(f"24 주석 {i}행: 형식이 달라 검사하지 못했다 — {l}")
        if m and cur:
            d, mz = cur[2][0], cur[1][1]
            want = (f"- 일간 **{d}** / 월지 **{mz}** (본기 {S.sipsin(d, S.BONGI[mz])}; 장간 "
                    + "·".join(f"{g}({S.sipsin(d, g)})" for g in S.JANGGAN_SCHOOLS["jangan_ga"][mz]) + ")")
            if l != want:
                problems.append(f"24 주석 {i}행: {l} ≠ {want}")
    if cases != 86 or notes != cases:
        problems.append(f"24 원전 명조 {cases}개·장간 주석 {notes}줄 — 86命 모두에 주석이 한 줄씩 있어야 한다")


# 3·4 ─ 30 조견표
def check_shinsal_doc():
    t = read("references/30_shinsal_extended.md")
    rows = table_rows(section(t, r"^### 2-2\."))
    head = rows[0][1:] if rows else []
    if [r[0] for r in rows[1:]] != list(S.ZHI) or set("".join(head).replace("·", "")) != set(S.GAN):
        problems.append(f"30 §2-2 십이운성표: 지지 12행·천간 10개 열이어야 한다 ({len(rows) - 1}행, 열 {' '.join(head)})")
    for r in rows[1:]:
        z = r[0]
        for col, val in zip(head, r[1:]):
            for g in col.split("·"):
                if S.unseong(g, z) != val:
                    problems.append(f"30 §2-2 십이운성 {g}{z}: 문서 {val} ≠ 코드 {S.unseong(g, z)}")
    rows = table_rows(section(t, r"^### 3-1\."))
    names = {"양인": S.YANGIN, "문창귀인": S.MUNCHANG, "학당귀인": S.HAKDANG, "금여": S.GEUMYEO, "홍염살": S.HONGYEOM}
    head = rows[0][1:11] if rows else []
    if head != list(S.GAN):
        problems.append(f"30 §3-1 머리줄 천간이 甲~癸 순이 아니다: {' '.join(head)}")
    seen = set()
    for r in rows[1:]:
        key = next((k for k in names if k in r[0]), None)
        if not key:
            continue
        seen.add(key)
        for g, val in zip(head, r[1:11]):
            want = names[key].get(g, "—")
            if val != want:
                problems.append(f"30 §3-1 {key} {g}: 문서 {val} ≠ 코드 {want}")
    if seen != set(names):
        problems.append(f"30 §3-1: {', '.join(k for k in names if k not in seen)} 행을 찾지 못했다 (행 이름·형식 확인)")
    m = re.search(r"\*\*천을귀인.*?\*\* — (.+)", t)
    if not m:
        problems.append("30 천을귀인 줄('**천을귀인(…)** — 甲·戊·庚 → 丑·未 / …')을 찾지 못했다")
    else:
        seen = []
        for part in m.group(1).split(" / "):
            gs, zs = part.split(" → ")
            for g in gs.split("·"):
                seen.append(g.strip())
                if set(zs.replace("·", "")) != set(S.CHEONEUL[g.strip()]):
                    problems.append(f"30 천을귀인 {g}: 문서 {zs} ≠ 코드 {S.CHEONEUL[g.strip()]}")
        if sorted(seen, key=S.GAN.index) != list(S.GAN):
            problems.append(f"30 천을귀인 줄이 10간을 한 번씩 덮지 않는다: {''.join(seen)}")
    n_sam = n_go = 0
    for r in table_rows(section(t, r"^### 3-2\.")):
        if r[0] in S.SAMJAE:
            n_sam += 1
            if r[1].replace(" → ", "") != S.SAMJAE[r[0]]:
                problems.append(f"30 §3-2 삼재 {r[0]}: 문서 {r[1]} ≠ 코드 {S.SAMJAE[r[0]]}")
        if len(r) == 3 and "·" in r[0] and r[0].replace("·", "") in S.GOSIN_GWASUK:
            n_go += 1
            key = r[0].replace("·", "")
            if (r[1], r[2]) != S.GOSIN_GWASUK[key]:
                problems.append(f"30 §3-2 고신·과숙 {r[0]}: 문서 {r[1]},{r[2]} ≠ 코드 {S.GOSIN_GWASUK[key]}")
    if (n_sam, n_go) != (len(S.SAMJAE), len(S.GOSIN_GWASUK)):
        problems.append(f"30 §3-2: 삼재 {n_sam}행·고신·과숙 {n_go}행을 읽었다 — {len(S.SAMJAE)}·{len(S.GOSIN_GWASUK)}행이어야 한다 (절 제목·표 형식 확인)")


# 5 ─ 삼형 명칭
HYEONG_NAMES = dict({k: v.split("(")[0] for k, v in S.SAMHYEONG.items()}, 子卯="무례지형")   # 子卯는 saju_calc 주석과 같다


def check_samhyeong():
    t = read("references/22_hapchung_shinsal.md")
    heads = dict((chars, nm) for nm, chars in re.findall(r"^[①②③④] ([가-힣]+)\([^)]*\)[^\n]*\n(?:(?![①②③④])[^\n]*\n)*?\s*→ (\S+) 삼형",
                                                         section(t, r"^### 4-1\."), re.M))
    if frozenset("子卯") not in S.HYEONG_PAIRS:
        problems.append("saju_calc.HYEONG_PAIRS에 子卯(무례지형)가 없다")
    docs = [("22번", t), ("SKILL.md", read("SKILL.md"))]         # github-linked/SKILL.md는 로더라 정본 줄이 없다
    for chars, short in HYEONG_NAMES.items():
        for doc, txt in docs:
            defs = re.findall(chars + r"\s*=\s*([가-힣]+)", txt)
            if not defs or any(d != short for d in defs):
                problems.append(f"{doc} 정본 줄 '{chars}={short}'이 아니다: {defs or '없음'} (errata #12)")
        if chars in S.SAMHYEONG and heads.get(chars) != short:
            problems.append(f"22번 §4-1 '→ {chars} 삼형' 머리 이름이 {heads.get(chars)} — {short}이어야 한다 (errata #12)")


# 6 ─ 조후 용신
KO = {"갑목": "甲", "을목": "乙", "병화": "丙", "정화": "丁", "무토": "戊", "기토": "己",
      "경금": "庚", "신금": "辛", "임수": "壬", "계수": "癸"}
SYL = dict(zip("갑을병정무기경신임계", S.GAN))
EL = {"목": "甲乙", "화": "丙丁", "토": "戊己", "금": "庚辛", "수": "壬癸",
      "木": "甲乙", "火": "丙丁", "土": "戊己", "金": "庚辛", "水": "壬癸"}
MON = dict(zip(["인월", "묘월", "진월", "사월", "오월", "미월", "신월", "유월", "술월", "해월", "자월", "축월"], S.MONTH_ZHI))
MON_HEAD = {z: m for m, z in MON.items()}
NAME = re.compile("|".join(KO))
GLOSS = re.compile(r"(?<![가-힣])[갑을병정무기경신임계]\(([甲乙丙丁戊己庚辛壬癸])[^)]*\)")    # 병(丙) → 丙
COMPOUND = re.compile(r"(?<![가-힣])([갑을병정무기경신임계]{2,3})[목화토금수]?(?![가-힣])")   # 무기토·병정·임계수·경신
QUAL = re.compile(r"과다|추가|혼잡|(?<![종적])합|인접")   # 원문 용신을 조건부로 꺼릴 때 쓰는 말(무계 합화, 병신 인접). 괄호 밖에 있어야 한다 — 종합·부적합의 '합'은 아니다
NO_STEM = re.compile(r"(?<![가-힣])무[갑을병정경신임계](?=\s*시|\)|\s*$)")   # '무갑'·'(무정 시)'는 無甲·無丁 — 戊甲이 아니다 (무계 합화의 무계는 戊癸)
SIPSIN_WORD = {"비견": ["비견"], "겁재": ["겁재"], "비겁": ["비견", "겁재"], "식신": ["식신"], "상관": ["상관"], "식상": ["식신", "상관"],
               "정재": ["정재"], "편재": ["편재"], "재성": ["정재", "편재"], "정관": ["정관"], "편관": ["편관"], "칠살": ["편관"],
               "관성": ["정관", "편관"], "관살": ["정관", "편관"], "정인": ["정인"], "편인": ["편인"], "인성": ["정인", "편인"]}
SIPSIN_RE = re.compile(r"(?<![가-힣])(" + "|".join(SIPSIN_WORD) + r")(?![가-힣])")
SRC = "tests/fixtures/qtbj_wikisource.txt"     # 維基文庫 窮通寶鑑 raw — johu_wonmun.json의 _source
SEASONS = ["三春", "三夏", "三秋", "三冬"]
MONTH_NO = {"正": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "七": 6, "八": 7, "九": 8, "十": 9, "十一": 10, "十二": 11}
BOLD = "'" * 3
ESSAY_START = ["金以至阴为体"]      # 论金 총론은 '== 论金 ==' 머리 없이 己 三冬 뒤에 붙어 있다 — 己土 단락에서 잘라 낸다
MK = re.compile(r"((?:十一|十二|十|正|二|三|四|五|六|七|八|九)+)月")
NUM = "正二三四五六七八九十一"
HZ = "[甲乙丙丁戊己庚辛壬癸]"
HE = "[木火土金水]?"
# 원문 순위 말 — 先X后Y·X先Y后·先X…次Y는 X가 Y보다 앞, Y次之·佐之·次取Y는 같은 문장의 앞 글자보다 뒤
PAIR = re.compile(r"先(?:用|取|看)?(" + HZ + ")" + HE + r"[^。；]{0,6}?(?:后|次(?:用|取|看)?)(" + HZ + ")|(" + HZ + ")先(" + HZ + ")后")
FOLLOW = re.compile(r"(" + HZ + ")" + HE + r"(?:又)?(?:次之|佐之|为佐|为辅|再次|辅佐|为臣)|次(?:用|取|看)(" + HZ + ")|取(" + HZ + ")" + HE + r"(?:辅佐|为佐|佐之)")
NAMED = re.compile(r"(" + HZ + ")" + HE + r"(?:为上|为主|为尊|为要|次之|佐之|为佐)|(" + HZ + ")(" + HZ + ")" + HE + r"(?:为上|为要)")
HEAD_NEXT = re.compile(r"(" + HZ + ")" + HE + r"(?:为主|为尊|为君)[，,]?(" + HZ + ")" + HE + r"(?:次之|为佐|佐之)")   # X为主，Y次之 → Y는 X 바로 다음
NEG = re.compile(r"(?:不用|忌|无|不宜|不可专用)(" + HZ + ")")
NEG_USE = re.compile(r"((?:" + HZ + HE + r")+)(?:不用|无用)|(?:不用|忌见?|不宜(?:乱用)?)(" + HZ + ")")   # 꺼리는 말 속 천간은 근거가 아니다
# 원문이 스스로 순위를 엇갈리게 말하는 달 — md 상황 분석에 따로 적어 두었다
RANK_EXEMPT = {("乙", "酉"): "上下月이 갈린다 — 「耑用癸水…又宜用丙，癸水次之」",
               ("壬", "未"): "원문이 「先用辛金癸水，次用甲木」과 「先辛后甲，次取癸水」로 스스로 엇갈린다"}
# 취용 글자가 그 달 '원문' 줄 인용에 글자로 나오지 않는 달
COVER_EXEMPT = {("癸", "未"): "壬", }         # 「宜比劫助身」의 比劫으로만 나온다 (10번 미월 상황 분석)
# 그 달 단락이 원문에 없어 계절 단락 전체에서 인용을 찾는 달 — md에 공통 단락임을 밝혀 두었다
SEASON_WIDE = {("乙", "丑"): "원문에 十二月乙木 단락이 없다",
               ("丁", "丑"): "三冬 결론 문장이 十一月丁火 단락 끝에 있다",
               ("丁", "亥"): "三冬 결론 문장(「三冬丁火，甲木为尊，庚金佐之」)이 十一月丁火 단락 끝에 있다"}


def _stems(cell, keep_paren=True):
    """칸 → 천간 목록. 천간 이름(병화)·한자(丙)·복합 약칭(무기토·병정·임계수)·오행 이름(화·화토·金)을 읽는다.
    keep_paren=False면 괄호 속 조건은 뺀다."""
    cell = NO_STEM.sub(" ", GLOSS.sub(r"\1", cell))
    if not keep_paren:
        cell = re.sub(r"\([^)]*\)", "", cell)
    out = []
    bare = re.sub(r"\([^)]*\)", " ", cell)          # 오행 이름은 괄호 밖에서만 — 괄호 속 '화국 시' 같은 조건은 천간이 아니다

    def comp(m):
        if NAME.fullmatch(m.group(0)):
            return m.group(0)
        out.extend(SYL[c] for c in m.group(1))
        return " "
    cell = COMPOUND.sub(comp, cell)
    out += [KO[k] for k in NAME.findall(cell)]
    cell = NAME.sub(" ", cell)
    out += re.findall("[甲乙丙丁戊己庚辛壬癸]", cell)
    bare = NAME.sub(" ", COMPOUND.sub(" ", bare))
    for m in re.finditer(r"(?<![가-힣])([목화토금수]{1,2})기?(?![가-힣])|([木火土金水])", bare):
        out += [s_ for c in (m.group(1) or m.group(2)) for s_ in EL[c]]
    return out


def _unqualified(item, day):
    """기신 항목 → 조건(QUAL) 없이 꺼리는 천간. 조건은 괄호 밖에서, '·'로 이은 앞 글자들까지 덮는다.
    십성 이름(비견·식상·관살 …)은 일간 day 기준 천간으로 읽는다."""
    parts = re.sub(r"\([^)]*\)", "", GLOSS.sub(r"\1", item)).replace("*", "").split("·")
    out = []
    for i, p in enumerate(parts):
        if any(QUAL.search(x) for x in parts[i:]):
            continue
        out += _stems(p) + [g for w in SIPSIN_RE.findall(p) for g in S.GAN
                            if (S.sipsin(day, g) if g != day else "비견") in SIPSIN_WORD[w]]
    return out


def _month_sections(txt):
    heads = list(re.finditer(r"^### .*?\((.)月生\)", txt, re.M))
    return {h.group(1): txt[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(txt)]
            for i, h in enumerate(heads)}


def _bullets(sec, title):
    m = re.search(r"^\*\*" + re.escape(title) + r"\*\*\s*\n(.*?)(?=^\*\*|^---|\Z)", sec, re.M | re.S)
    return None if not m else [l for l in m.group(1).splitlines() if l.startswith("- ")]


def _bullet_stems(lines):
    return [s_ for l in lines if l.startswith("- **") for s_ in _stems(re.match(r"- \*\*(.+?)\*\*", l).group(1), keep_paren=False)]


def _months_of(marker):
    """원문 단락 머리 正二月甲木 → 인월 기준 달 번호 {0, 1}. 十一二月은 동짓달·섣달."""
    m = re.match(r"((?:十一|十二|十|正|二|三|四|五|六|七|八|九)+)月", marker)
    if not m:
        return set()
    if m.group(1) == "十一二":
        return {10, 11}
    return {MONTH_NO[t] for t in re.findall("十一|十二|十|正|二|三|四|五|六|七|八|九", m.group(1))}


def source_blocks():
    """(천간, 지지) → (계절 단락 전체, 그 달 인용이 있어야 할 글 = 계절 머리말 + 그 달을 덮는 단락)."""
    src = read(SRC)
    pos = sorted((src.index("== 论" + g), g) for g in S.GAN)
    out = {}
    for i, (st, g) in enumerate(pos):
        blk = src[st: pos[i + 1][0] if i + 1 < len(pos) else len(src)]
        for e in ESSAY_START:
            if e in blk:
                blk = blk[: blk.index(e)]
        for si, sname in enumerate(SEASONS):
            m = re.search("=== " + sname + r"[^=]*===(.*?)(?=\n=== |\n== |\Z)", blk, re.S)
            season = m.group(1) if m else ""
            parts = re.split("(" + BOLD + "[^']+" + BOLD + ")", season)
            for k in range(3):
                mi = si * 3 + k
                z = S.MONTH_ZHI[mi]
                paras = [parts[j] + parts[j + 1] for j in range(1, len(parts), 2) if mi in _months_of(parts[j].strip("'"))]
                allowed = season if (g, z) in SEASON_WIDE else parts[0] + "".join(paras)
                out[g, z] = (season.replace(BOLD, ""), allowed.replace(BOLD, ""))
    return out


def _rank_problems(g, z, q, order):
    """json 인용의 순위 말 ↔ order. 인용 속 순위가 order와 어긋나면 그 까닭을 돌려준다."""
    out = []
    for m in NAMED.finditer(q):
        for s_ in filter(None, m.groups()):
            if s_ != g and s_ not in order:
                out.append(f"인용이 순위를 매긴 {s_}(「{m.group(0)}」)이 취용 순서 {''.join(order)}에 없다")
    if (g, z) in RANK_EXEMPT:
        return out
    for m in PAIR.finditer(q):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if a in order and b in order and order.index(a) > order.index(b):
            out.append(f"「{m.group(0)}」는 {a}가 {b}보다 앞인데 취용 순서는 {''.join(order)}")
    for m in FOLLOW.finditer(q):
        y = m.group(1) or m.group(2) or m.group(3)
        pre = q[q.rfind("。", 0, m.start()) + 1: m.start()]
        neg = {n.group(1) for n in NEG.finditer(pre)}
        for x in dict.fromkeys(c for c in pre if c in order and c not in (g, y) and c not in neg):
            if y in order and order.index(x) > order.index(y):
                out.append(f"「{m.group(0)}」는 {y}가 {x} 뒤인데 취용 순서는 {''.join(order)}")
    for m in HEAD_NEXT.finditer(q):
        x, y = m.groups()
        if x in order and (y not in order or order.index(y) != order.index(x) + 1):
            out.append(f"「{m.group(0)}」는 {y}가 {x} 바로 다음인데 취용 순서는 {''.join(order)}")
    return out


def _anchor_problems(z, q, allowed):
    """인용이 그 달 자리에서 시작하는가 — 달 숫자 중간·다른 달 첫머리·다른 달 표시 뒤에서 자른 인용을 잡는다."""
    out, i, k = [], S.MONTH_ZHI.index(z), allowed.find(q)
    lead = re.match(r"(?:总之[，,]?)?" + MK.pattern, q)
    if k > 0 and allowed[k - 1] in NUM and re.match("[" + NUM + "]*月", q):
        out.append(f"인용이 원문의 달 숫자 중간에서 시작한다(「{allowed[k - 1]}{q[:6]}…」)")
    if lead and i not in _months_of(lead.group(1) + "月"):
        out.append(f"인용 첫머리 {lead.group(1)}月이 {MON_HEAD[z]}이 아니다")
    if k >= 0 and not lead:
        prev = list(MK.finditer(allowed[allowed.rfind(chr(10), 0, k) + 1: k]))
        if prev and i not in _months_of(prev[-1].group(0)):
            out.append(f"인용 바로 앞의 달 표시가 {prev[-1].group(0)}이다 — 다른 달 문장")
    return out


def check_johu():
    table = json.loads(read("references/johu_wonmun.json"))["table"]
    src = source_blocks()
    files = sorted(glob.glob(os.path.join(REF, "0[1-9]_gungbok_*.md"))) + sorted(glob.glob(os.path.join(REF, "10_gungbok_*.md")))
    for g, f in zip(S.GAN, files):
        txt = open(f, encoding="utf-8").read()
        name = os.path.basename(f)
        secs = _month_sections(txt)
        if sorted(secs) != sorted(S.MONTH_ZHI):
            problems.append(f"{name}: 월별 절(### X월생(…月生)) 12개를 찾지 못했다 ({len(secs)}개)")
        rows = re.findall(r"^\| (" + "|".join(MON) + r") \|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", txt, re.M)[:12]
        if [MON[r[0]] for r in rows] != list(S.MONTH_ZHI):
            problems.append(f"{name}: 조후 매트릭스 12행(인월~축월 순)을 찾지 못했다 ({len(rows)}행)")
        for m, _season, yong, hui, gi in rows:
            z = MON[m]
            order = table[g][z]["order"]
            ys, hs = _stems(yong, keep_paren=False), _stems(hui, keep_paren=False)    # 괄호 속 조건으로 내린 취용 글자는 빠진 것으로 본다
            if order[0] not in ys:
                problems.append(f"{name} {m}: 원문 1순위 {order[0]}이 용신 칸에 없다")
            for s_ in order:
                if s_ not in ys + hs and s_ != g:
                    problems.append(f"{name} {m}: 원문 취용 {s_}이 용신·희신 칸에 없다")
            for s_ in _stems(yong, keep_paren=False):
                if s_ not in order:
                    problems.append(f"{name} {m}: 용신 칸 {s_}이 원문 취용 순서({''.join(order)})에 없다")
            seq = list(dict.fromkeys(s_ for s_ in _stems(yong + "," + hui, keep_paren=False) if s_ in order))
            if seq != [s_ for s_ in order if s_ in seq]:
                problems.append(f"{name} {m}: 매트릭스 용신·희신 순서 {''.join(seq)} ≠ 원문 취용 순서 {''.join(order)}")
            sec = secs.get(z, "")
            by, bh, bg = (_bullets(sec, t) for t in ("용신 (用神)", "희신 (喜神)", "기신 (忌神)"))
            if by is None or bh is None or bg is None:
                problems.append(f"{name} {m}: 본문에 용신·희신·기신 목록이 없다")
                continue
            # 본문 기신은 굵은 이름과 그 뒤 꾸밈말까지 — ' — '나 ':' 뒤의 설명 속 '과다'는 조건이 아니다
            items = [p.strip() for p in re.split(r"[,，/、]", gi)] + [re.match(r"(\*\*.+?\*\*)?(.*?)(?: — |[:：]|$)", l[2:]).group(0) for l in bg]
            for it in items:
                bad = [s_ for s_ in _unqualified(re.sub(r"(?: — |[:：])$", "", it), g) if s_ in order]
                if bad:
                    problems.append(f"{name} {m}: 기신 '{it}'에 원문 용신 {bad[0]} (조건 없음 — '과다'·'추가' 등을 괄호 밖에)")
            if set(_bullet_stems(by)) != set(_stems(yong, keep_paren=False)):
                problems.append(f"{name} {m}: 본문 용신 {''.join(_bullet_stems(by))} ≠ 매트릭스 용신 {''.join(_stems(yong, keep_paren=False))}")
            if not set(_stems(hui, keep_paren=False)) <= set(_bullet_stems(bh)) | {g}:
                problems.append(f"{name} {m}: 매트릭스 희신 {''.join(_stems(hui, keep_paren=False))}가 본문 희신 {''.join(_bullet_stems(bh))}에 없다")
            for l in by + bh:
                b = re.match(r"- \*\*(.+?)\*\*(?: [^—\n]{1,12}?)? — ([1-4](?:·[1-4])*)순위", l)   # '**계수** 비견 — 4순위'도 읽는다
                if b:
                    want = [order.index(s_) + 1 if s_ in order else None for s_ in _stems(b.group(1), keep_paren=False)]
                    if want != [int(x) for x in b.group(2).split("·")]:
                        problems.append(f"{name} {m}: '{b.group(1)}' {b.group(2)}순위 ≠ 원문 취용 순서상 {want}")
        for z in S.MONTH_ZHI:
            q, order = table[g][z]["quote"], table[g][z]["order"]
            plain, allowed = src[g, z]
            season = SEASONS[S.MONTH_ZHI.index(z) // 3]
            if q not in allowed:
                problems.append(f"{name} {MON_HEAD[z]}: json 인용이 원문 그 달 단락(또는 {season} 머리말)에 없다 — {q[:20]}…")
            if order[0] != g and order[0] not in q:
                problems.append(f"{name} {MON_HEAD[z]}: json 인용에 원문 1순위 {order[0]}이 없다 — 취용 근거 문장을 인용할 것")
            for why in _anchor_problems(z, q, allowed) + _rank_problems(g, z, q, order):
                problems.append(f"{name} {MON_HEAD[z]}: {why}")
            for s_ in order:
                if s_ != g and s_ not in plain:
                    problems.append(f"{name} {MON_HEAD[z]}: 취용 {s_}이 원문 {season}{g} 단락에 한 번도 나오지 않는다")
            sec = secs.get(z, "")
            wl = re.search(r"^\*\*원문 \(窮通寶鑑\)\*\*: (.+)$", sec, re.M)
            if not wl or f"「{q}」" not in wl.group(1):
                problems.append(f"{name} {MON_HEAD[z]}: johu_wonmun.json 원문 인용이 그 달 '원문' 줄에 그대로 없다")
            quotes = re.findall(r"「([^」]+)」", wl.group(1) if wl else "")
            for qq in quotes:
                if qq not in allowed:
                    problems.append(f"{name} {MON_HEAD[z]}: '원문' 줄 인용 「{qq[:20]}…」이 원문 그 달 단락에 없다")
            cited = NEG_USE.sub(" ", "　".join(quotes))
            for s_ in order:
                if s_ != g and s_ not in cited and COVER_EXEMPT.get((g, z)) != s_:
                    problems.append(f"{name} {MON_HEAD[z]}: 취용 {s_}의 근거가 '원문' 줄 인용에 없다 (꺼리는 말 속 글자는 근거가 아니다)")
            ol = re.search(r"^\*\*원문 취용 순서\*\*: (.+)$", sec, re.M)
            got = None
            if ol:                                        # 괄호 밖 '→'로만 나눈다 — 괄호 속 주석의 '경금 → 정화'는 순서가 아니다
                parts, depth, cur = [], 0, ""
                for ch in ol.group(1).strip():
                    depth += (ch == "(") - (ch == ")")
                    if ch == "→" and depth == 0:
                        parts.append(cur); cur = ""
                    else:
                        cur += ch
                parts.append(cur)
                got = []
                for part in parts:
                    m2 = re.match(r"\s*[가-힣]{2}\(([甲乙丙丁戊己庚辛壬癸])", part)
                    if not m2:
                        problems.append(f"{name} {MON_HEAD[z]}: '원문 취용 순서' 항목 '{part.strip()}'에 한자 표기(예: 병화(丙))가 없다")
                    got.append(m2.group(1) if m2 else "?")
            if got != order:
                problems.append(f"{name} {MON_HEAD[z]}: '원문 취용 순서' {''.join(got or [])} ≠ json order {''.join(order)}")


# 7 ─ 마크다운 표
SEP = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")


def check_tables(paths):
    for p in paths:
        lines = open(p, encoding="utf-8").read().splitlines()
        fence, i, rel = False, 0, os.path.relpath(p, ROOT)
        while i < len(lines):
            l = lines[i]
            if l.strip().startswith("```"):
                fence = not fence
            if not fence and l.lstrip().startswith("|"):
                j = i
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    j += 1
                block = lines[i:j]
                if len(block) < 2 or not SEP.match(block[1].strip()):
                    problems.append(f"{rel} {i + 1}행: 머리줄·구분줄이 없는 표 조각 (빈 줄로 끊긴 표?)")
                else:
                    n = block[0].strip().strip("|").count("|")
                    for k, row in enumerate(block[2:], i + 3):
                        if row.strip().replace("\\|", "").strip("|").count("|") != n:
                            problems.append(f"{rel} {k}행: 표 열 수가 머리줄과 다르다")
                i = j
                continue
            i += 1


# 8 ─ 경로 참조
BARE_DIRS = ["", "references", "scripts", "tests", "tests/fixtures", "web", "github-linked", ".github/workflows"]
BARE_OK = {"CLAUDE.md", "AGENTS.md"}            # 다른 도구의 관례 파일 이름을 설명할 때


def check_paths():
    docs = ["SKILL.md", "github-linked/SKILL.md", "README.md", "web/README.md"]
    for doc in docs + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(REF, "*.md"))):
        txt = read(doc)
        for ref in sorted(set(re.findall(r"(?:references|scripts|tests|web)/[\w./-]+\.(?:md|py|json|html|mjs)", txt))):
            if not os.path.exists(os.path.join(ROOT, ref)):
                problems.append(f"{doc}: 없는 파일 참조 {ref}")
        # 디렉터리 없이 쓴 파일 이름(`29_sibisinsal.md`, 24_japyeong_cases.md) — 저장소 어딘가에 있어야 한다
        for ref in sorted(set(re.findall(r"(?<![\w/.-])([\w-]+\.(?:md|py|json|html|mjs))(?![\w/])", txt))):
            if ref not in BARE_OK and not any(os.path.exists(os.path.join(ROOT, d, ref)) for d in BARE_DIRS):
                problems.append(f"{doc}: 없는 파일 참조 {ref}")


# 9 ─ 웹 표 구획
def check_web():
    import build_web_tables as B
    html = read("web/unui-sigantable.html")
    a, b = html.index(B.BEGIN), html.index(B.END) + len(B.END)
    if html[a:b] != B.block():
        problems.append("web/unui-sigantable.html 표 구획이 saju_calc.py와 다르다 — python3 scripts/build_web_tables.py")


def main():
    check_janggan_doc()
    check_corpus_notes()
    check_shinsal_doc()
    check_samhyeong()
    check_johu()
    check_tables([os.path.join(ROOT, "SKILL.md"), os.path.join(ROOT, "github-linked", "SKILL.md"),
                  os.path.join(ROOT, "README.md")] + sorted(glob.glob(os.path.join(REF, "*.md"))))
    check_paths()
    if "--skip-web" not in sys.argv:
        check_web()
    if problems:
        print(f"일치 검사 실패 {len(problems)}건")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("일치 검사 통과")


if __name__ == "__main__":
    main()
