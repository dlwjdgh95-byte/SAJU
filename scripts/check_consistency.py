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
     - 원문 사본(tests/fixtures/qtbj_wikisource.txt)은 SRC_SHA256으로 고정한다 — 바뀌면 실패
     - johu_wonmun.json 인용·취용 ↔ 窮通寶鑑 원문(tests/fixtures/qtbj_wikisource.txt): 인용은 그 달 단락이나 계절 머리말에, 취용 글자는 계절 단락에 있어야 한다
       그 달 단락이 있으면 json 인용은 그 단락(또는 그 달 N月로 시작하는 머리말 문장)에서, 1순위 글자를 담아야 한다
       json·'원문' 줄 인용 모두 그 달 자리에서 시작해야 하고(달 숫자·첫머리 N月·바로 앞 달 표시·조건 말 或若如凡 바로 뒤가 아님), 그 인용들과
       그 달 N月(또는 그 계절 이름 三秋甲木)으로 시작하는 원문 문장의 순위 말(先X后Y·无X用Y·取X辅Y·XY为要·Y次之·X为主·X为先)이 order와 맞아야 하고,
       첫 으뜸 말(先X·专用X·独爱X·X为用 …)은 1순위, 次·佐로 둔 글자는 1순위가 아니어야 한다.
       조건문(或·若·凡·如, 문장 머리의 「…者，」「X多、」「无X用Y」, '원문' 줄에 '조건 「…」'으로 적은 인용)은 순위로 읽지 않는다
     - references/01~10 월별 원문 줄(한 줄, 「」 전부, 취용 글자가 모두 근거로 나오는지)·취용 순서 줄(항목의 한글 이름과 한자가 맞는지 포함)·매트릭스(순서 포함)·본문 용신·희신(N순위)·기신 목록(십성 이름 포함) ↔ json.
       줄임표(…)로 덜어 낸 인용도 첫 조각 자리에서 시작 위치를 본다.
       같은 (X月生) 머리가 두 번 있거나, 한 달에 '원문' 인용 줄(**원문**:·**원문 (…)**: 등)·'원문 취용 순서' 줄이 둘 이상이거나,
       '원문 취용 순서' 줄이 '원문' 줄 바로 다음 줄이 아니면 실패(둘째 줄·사이에 끼운 줄은 읽지 않으므로)
     - errata로 바로잡은 문장·표 행(ERRATA_PINNED — 요약·비교 문장, 매트릭스 행, 미월 계절 칸·계절 줄 「늦여름」)과 그 달 '원문' 줄 인용(WONMUN_PINNED)이 빠지면 실패
     - 본문 산문의 순서 표기('A → B → C' 화살표·「A·B 순」·先X後Y 등)와 매트릭스 계절 칸은 '확인 권장'으로만 알린다(errata #40).
       대신 01~10 본문은 tests/fixtures/johu_docs.json이 절마다 고정한다(tests/build_fixtures.py --johu로만 갱신 — 갱신할 때 확인 권장·실패를 함께 출력)
     - 원문이 순위 말을 두지 않은 글자 쌍은 여기서 잡을 수 없으므로 tests/test_calc.py의 JOHU_PINNED가 120개월 order를 고정한다
  7. 마크다운 표 깨짐 (빈 줄로 끊긴 표 등)
  8. SKILL.md·README·references/*.md가 가리키는 파일의 존재 (경로를 쓴 참조와 파일 이름만 쓴 참조 모두)
  9. 웹 엔진 표 구획이 최신인지 (scripts/build_web_tables.py --check와 같음)
"""

import glob, hashlib, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import saju_calc as S  # noqa: E402

REF = os.path.join(ROOT, "references")
problems = []
notes = []        # 확인 권장 — 실패로 치지 않는다(본문 산문의 순서 표기·계절 칸 낱말). 01~10 본문 자체는 tests/fixtures/johu_docs.json이 고정한다


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
COMPOUND = re.compile(r"(?<![가-힣])(?!(?:경계|기신|정신)(?![가-힣(]))([갑을병정무기경신임계]{2,3})[목화토금수]?(?![가-힣])")   # 무기토·병정·임계수·경신 (경계·기신·정신은 낱말)
QUAL = re.compile(r"과다|과잉|과왕|과중|과강|과도|태과|태다|태왕|범람|넘|다수|다량|다견|많|왕성|중중|중첩|중복|일파|추가|혼잡|多|(?<![종적])합|인접")   # 원문 용신을 조건부로 꺼릴 때 쓰는 말(무계 합화, 병신 인접). 괄호 밖에 있어야 한다 — 종합·부적합의 '합'은 아니다
NO_STEM = re.compile(r"(?<![가-힣])무[갑을병정경신임계](?=\s*시|\)|\s*$)")   # '무갑'·'(무정 시)'는 無甲·無丁 — 戊甲이 아니다 (무계 합화의 무계는 戊癸)
SIPSIN_WORD = {"비견": ["비견"], "겁재": ["겁재"], "비겁": ["비견", "겁재"], "식신": ["식신"], "상관": ["상관"], "식상": ["식신", "상관"],
               "정재": ["정재"], "편재": ["편재"], "재성": ["정재", "편재"], "정관": ["정관"], "편관": ["편관"], "칠살": ["편관"],
               "관성": ["정관", "편관"], "관살": ["정관", "편관"], "정인": ["정인"], "편인": ["편인"], "인성": ["정인", "편인"]}
SIPSIN_RE = re.compile(r"(?<![가-힣])(" + "|".join(SIPSIN_WORD) + r")(?![가-힣])")
SRC = "tests/fixtures/qtbj_wikisource.txt"     # 維基文庫 窮通寶鑑 raw — johu_wonmun.json의 _source
SRC_SHA256 = "8ba17242f116583de2e10172e006f5ce5f74b23ccfc0bd24b886be135e9f20bd"   # 원문 사본이 바뀌면 모든 대조의 기준이 바뀐다 — 다시 받았을 때만 고친다
SEASONS = ["三春", "三夏", "三秋", "三冬"]
MONTH_NO = {"正": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "七": 6, "八": 7, "九": 8, "十": 9, "十一": 10, "十二": 11}
BOLD = "'" * 3
ESSAY_START = ["金以至阴为体"]      # 论金 총론은 '== 论金 ==' 머리 없이 己 三冬 뒤에 붙어 있다 — 己土 단락에서 잘라 낸다
MK = re.compile(r"((?:十一|十二|十|正|二|三|四|五|六|七|八|九)+)月")
NUM = "正二三四五六七八九十一"
HZ = "[甲乙丙丁戊己庚辛壬癸]"
HE = "[木火土金水]?"
RUN = "((?:" + HZ + HE + ")+)"
STEMS = "甲乙丙丁戊己庚辛壬癸"
# 원문 순위 말 — 先X后Y·X先Y后·先X…次Y·先X…后用Y·无X用Y는 X가 Y보다 앞, 取Y辅X는 X가 Y보다 앞
PAIR = re.compile(r"先(?:用|取|看)?(" + HZ + ")" + HE + r"[^。；]{0,6}?(?:后|次)(?:用|取|看)?(" + HZ + ")|(" + HZ + ")先(" + HZ + ")后"
                  r"|无(" + HZ + ")" + HE + r"[^。；，]{0,2}?用(" + HZ + ")|取(" + HZ + ")" + HE + "辅(" + HZ + ")"
                  r"|(?<![甲乙丙丁戊己庚辛壬癸木火土金水])(" + HZ + ")" + HE + "(" + HZ + ")" + HE + "为(?:要|上)")    # 庚丁为要·丙甲为上 — 앞 글자가 먼저
# 뒤에 오는 글자 — XY次之·XY为佐·次用XY·取Y辅佐의 Y(여럿이면 모두)는 같은 문장의 앞 글자와 앞 문장들의 으뜸 글자보다 뒤
FOLLOW = re.compile(RUN + r"(?:又)?(?:次之|佐之|为佐|为辅|再次|辅佐|为臣)|次(?:用|取|看)" + RUN + "|取(" + HZ + ")" + HE + r"(?:辅佐|为佐|佐之)")
# 酌用·亦不可少·参酌 — 같은 문장의 앞 글자보다 뒤라는 순서만 본다(order에 없어도 된다)
WEAK = re.compile(RUN + r"(?:亦)?(?:权宜)?(?:酌用|亦不可少|不可少|参酌)")
# 으뜸 말 — 先X·专用X·耑用X·独爱X·X为尊/为主/为最/为先/为用/为专·XY为要/为上의 X. X先Y后의 先, 专用XY의 둘 이상 글자,
# 木盛先庚처럼 형편을 단 先(盛·多·旺·重 뒤)은 으뜸 말이 아니다
NOT_AFTER = "(?<![甲乙丙丁戊己庚辛壬癸木火土金水])"
HEADW = re.compile(NOT_AFTER + r"(?<![盛多旺重])先(?:用|取|看)?(" + HZ + ")|(?:专|耑|端)(?:用|取)(" + HZ + ")" + HE + "(?!" + HZ + ")"
                   r"|独(?:爱|用|取)(" + HZ + ")|" + NOT_AFTER + "(" + HZ + ")" + HE + r"为(?:尊|主|最|先|用|专)"
                   r"|" + NOT_AFTER + "(" + HZ + ")" + HE + HZ + HE + "为(?:要|上)")
NAMED = re.compile(r"(" + HZ + ")" + HE + r"(?:为上|为主|为尊|为要|为先|次之|佐之|为佐)|(" + HZ + ")(" + HZ + ")" + HE + r"(?:为上|为要)")
HEAD_NEXT = re.compile(r"(" + HZ + ")" + HE + r"(?:为主|为尊)[，,]?(" + HZ + ")" + HE + r"(?:次之|为佐|佐之)")   # X为主，Y次之 → Y는 X 바로 다음 (为君·为佐는 임금과 보좌라 순위가 아니다)
# 맨 无X는 꺼리는 말이 아니다 — 「无癸曰旱田」은 癸가 없으면 안 된다는 말이다(无X亦可·无X用Y는 따로 읽는다)
NEG = re.compile(r"(?:不用|忌|不宜|不可专用)(" + HZ + ")")
NEG_USE = re.compile(RUN + r"(?:不用|无用|不可为用|不可用)|(?:不用|忌见?|不宜(?:乱)?用?|防|怕|不见|不可专用|所忌者)" + RUN     # 꺼리는 말 속 천간은 근거가 아니다
                     + r"|(?:以|见)" + RUN + "为病|为" + RUN + "之病|无" + RUN + "亦可|恐" + RUN + r"[^。，]{0,6}为病"
                     + "|" + RUN + r"[^。，；]{0,4}[，,]为[木火土金水]{1,2}之病|见" + RUN + "则否|" + RUN + r"一透[，,][^。，]{0,4}不全")
EXAM = re.compile("科甲|甲第|甲科")          # 과거 급제를 이르는 말 속 甲은 천간이 아니다
NOT_FIRST = re.compile(r"不可专用(" + HZ + ")")     # 不可专用X — X는 1순위가 아니다
# 조건문 — 그 조건에서의 취용이라 그 달 순위로 읽지 않는다. 或·若·凡·如와, 문장 머리의 「化金者，」「甲多、」「无甲用庚」
COND = re.compile(r"\s*(?:或|若|凡|如|[^，。、,]{1,6}者[，,]|(?:[甲乙丙丁戊己庚辛壬癸][木火土金水]?){1,2}(?:太|过)?多[、，,]|无[甲乙丙丁戊己庚辛壬癸][木火土金水]?(?:则)?(?:用|取))")
LEAD = re.compile(r"(?:总之[，,]?|故)?" + MK.pattern)
# 원문이 스스로 순위를 엇갈리게 말하는 달과 그 글자 쌍 — md 상황 분석에 따로 적어 두었다. 다른 쌍의 순위는 그대로 본다.
# 둘째 값이 True인 달만 json 인용 자체가 엇갈리는 두 문장을 담는다 — 나머지 달의 json 인용은 예외 없이 order와 맞아야 한다
RANK_EXEMPT = {("乙", "午"): ({frozenset("丙癸")}, True, "三夏 머리말 「五六月先丙后癸」와 오월 단락 「余皆用癸水为先」가 엇갈리고, json 인용도 「柱多金水，丙火为先，余皆用癸水为先」을 함께 담는다"),
               ("乙", "酉"): ({frozenset("丙癸")}, True, "上下月이 갈린다 — 「耑用癸水…又宜用丙，癸水次之」"),
               ("乙", "申"): ({frozenset("丙己")}, True, "「七月喜己土为用」이 己를 앞세우지만 같은 단락이 丙 투간을 「科甲」, 己+丙을 「上命」이라 하고 三秋 머리말이 「先丙后癸」다"),
               ("壬", "未"): ({frozenset("甲癸")}, True, "「先用辛金癸水，次用甲木」과 「先辛后甲，次取癸水」가 甲·癸 순서에서 엇갈린다"),
               ("癸", "寅"): ({frozenset("辛庚"), frozenset("丙庚")}, False, "「先用辛金…次用丙火」와 「辛金为主，庚金次之，丙亦不可少」가 丙·庚 순서에서 엇갈린다 — 그래서 「辛金为主，庚金次之」의 庚이 辛 바로 다음이 아닌 것(辛·庚 쌍)도 뺀다"),
               ("己", "戌"): ({frozenset("甲癸")}, True, "三秋 공통 「先癸后丙」 뒤에 「九月土盛，宜甲木疏之」가 九月만 甲을 앞세운다")}
# 그 달 단락이 있는데도 json 인용을 계절 머리말(三秋甲木 같은 달 숫자 없는 단락 포함)에서 가져온 달 — 그 달 단락에 취용 순서를 밝힌 문장이 없을 때만.
# 머리말 문장 중간에 그 달이 나오는 인용(「…七月甲堪为戟…」)도 N月로 시작하지 않으면 여기에 올려야 통과한다. 지금은 비어 있다
PREFACE_OK = {}
# RANK_EXEMPT 달마다 md 그 달 절에 엇갈림을 밝힌 문장 — 이 문장이 빠지면 면제의 근거가 사라진다
RANK_EXEMPT_NOTE = {("乙", "午"): "원문이 스스로 갈리는 곳",
                    ("乙", "酉"): "추분 후에는 병화를 먼저",
                    ("乙", "申"): "원문이 스스로 엇갈리는 대목",
                    ("壬", "未"): "두 문장이 甲·癸 순서에서 엇갈린다",
                    ("癸", "寅"): "경금은 신금이 없을 때의 대용(3순위)",
                    ("己", "戌"): "「九月土盛，宜甲木疏之，余皆酌用」을 더한다"}
# 매트릭스 계절 칸의 첫말 — 인월부터. 같은 뜻의 다른 낱말도 있어 확인 권장으로만 낸다
SEASON_CELL = ["초봄", "봄 극성", "늦봄", "초여름", "한여름", "늦여름", "초가을", "가을 극성", "늦가을", "초겨울", "한겨울", "늦겨울"]
JOHU_FILES = ["01_gungbok_gapmok.md", "02_gungbok_eulmok.md", "03_gungbok_byunghwa.md", "04_gungbok_junghwa.md",
              "05_gungbok_muto.md", "06_gungbok_gito.md", "07_gungbok_gyunggeum.md", "08_gungbok_singeum.md",
              "09_gungbok_imsu.md", "10_gungbok_gyesu.md"]      # 일간 차례 — 다른 이름의 사본이 끼어도 일간이 밀리지 않는다
# errata로 고친 요약·비교 문장 가운데 검사기가 뜻으로 읽지 못하는 것 — 되돌리면 실패한다. 고칠 때는 errata와 함께 이 목록도 고친다
ERRATA_PINNED = [
    ("09_gungbok_imsu.md", "묘·사월은 신금이 경금보다 앞서고 미월은 신금만 쓴다", "#36 ⑦"),
    ("10_gungbok_gyesu.md", "갑목은 계수 → 정화 → 경금(미월은 계수 없이 정화·경금), 을목은 계수(미월은 병화가 먼저)", "#36 ⑦"),
    ("10_gungbok_gyesu.md", "을목·기토 겨울의 1순위, 무토는 자·축월 1순위(해월은 갑목 다음)", "#36 ⑦"),
    ("02_gungbok_eulmok.md", "사·술월엔 신금, 신월엔 기토, 유월엔 정화가 더해진다", "#37 ·#38 ④"),
    ("02_gungbok_eulmok.md", "단 사·술월은 병화 없이 계수·신금이고(사월은 경금까지)", "#37"),
    ("10_gungbok_gyesu.md", "계수는 병화 해동(해월은 병화 없이 경신)", "#38 ④"),
    ("03_gungbok_byunghwa.md", "무토는 11월엔 임수의 보좌(「壬水为最，戊土佐之」), 10월엔 갑·경과 함께 투간하면 귀하고", "#34 ⑧·#43"),
    ("03_gungbok_byunghwa.md", "1·2·7월엔 임수가 많을 때만 제방으로 쓴다", "#34 ⑧·#43"),
    ("04_gungbok_junghwa.md", "8월 甲丙庚(취용 순서는 甲庚丙)", "#34 ⑧"),
    ("06_gungbok_gito.md", "계수가 기토의 단비** — 사·오·미·신·유월은 1순위, 묘·진·술월은 2순위, 겨울엔 쓰지 않음", "#34 ⑧"),
    ("06_gungbok_gito.md", "여름과 칠·팔월(사·오·미·신·유월)엔 계수가 생명을 주는 단비(1순위 용신 — 술월은 갑목 다음 2순위)", "#40"),
    ("07_gungbok_gyunggeum.md", "인·묘·진·미·신·유·해·자·축 아홉 달의 취용 순서에 정화를 넣는다", "#32 ①"),
    ("07_gungbok_gyunggeum.md", "원문 아홉 달의 취용에 들며", "#32 ①"),
    ("07_gungbok_gyunggeum.md", "정화가 완성시킴(원문 아홉 달 취용)", "#32 ①"),
    ("09_gungbok_imsu.md", "해월 임수는 무토가 먼저, 병화가 온기를 더하며, 갑목이 무토를 칠 때 경금이 무토를 지킨다", "#29 ②"),
    ("09_gungbok_imsu.md", "병화가 임수를 보면 귀하다는 말은 후대의 풀이이고, 궁통보감 원문 문장은 아니다", "#39 ②"),
    ("07_gungbok_gyunggeum.md", "인월(暖庚性)·축월(解冻)은 1순위, 묘·사·유·해·자월은 보좌", "#34 ⑧"),
    ("10_gungbok_gyesu.md", "- 목일간: 갑목은 경금·정화(벽갑인정), 을목은 병화로 온기", "#34 ⑧"),
    ("03_gungbok_byunghwa.md", "지지 신(申)에 장생의 물이 있으면", "#41"),
    ("09_gungbok_imsu.md", "묘월·사월에는 신금을 경금보다 앞에 두며, 미월에는 경금 없이 신금만 쓴다", "#41"),
    ("10_gungbok_gyesu.md", "경금(庚金) 중심 (묘·사월은 신금이 앞, 미월은 신금만)", "#41"),
    ("02_gungbok_eulmok.md", "신금(계수의 근원 — 사월은 경금까지), 신월에는 기토, 유월에는 정화", "#41"),
    ("05_gungbok_muto.md", "미월은 계수·병화 다음에, 축월은 병화 다음에 갑목을 쓴다", "#41"),
    ("05_gungbok_muto.md", "겨울엔 병화가 중심(해월은 갑목 다음, 자·축월은 1순위)", "#41"),
    ("06_gungbok_gito.md", "토왕월(진·미·술·축) 가운데 진월은", "#41"),
    ("06_gungbok_gito.md", "겨울·정월·진월엔 으뜸", "#41"),
    ("04_gungbok_junghwa.md", "을목 → 병화로 햇빛을 받고 계수로 적신다", "#41"),
    ("02_gungbok_eulmok.md", "다만 사·술월은 병화 없이 계수·신금이고, 겨울(해·자·축월)은 계수 없이 병화가 으뜸이다", "#42"),
    ("04_gungbok_junghwa.md", "칠·팔월에만 갑목이 없을 때 「枯草引灯」", "#42"),
    ("04_gungbok_junghwa.md", "칠·팔월엔 갑목이 없을 때 「枯草引灯」", "#42"),
    ("04_gungbok_junghwa.md", "을목은 칠·팔월에만 병화와 함께 대용", "#42"),
    ("07_gungbok_gyunggeum.md", "인·축월 1순위(暖庚·解冻), 묘·사·유·해·자월 보좌", "#42"),
    ("08_gungbok_singeum.md", "인·축월 한기를 푸는 1순위, 묘·사·유·해·자월 보좌", "#42"),
    ("09_gungbok_imsu.md", "인·진·유·해월은 경금, 묘·사월은 신금이 경금보다 앞서고", "#42"),
    ("10_gungbok_gyesu.md", "갑·을목 사·오월, 기토 여름, 무토 미월, 임수 오월의 1순위 용신(을목 미월은 병화 다음, 경금 오월은 임수 다음)", "#42·#44"),
    ("10_gungbok_gyesu.md", "기둥에 戌·未가 둘씩 있고", "#42"),
    ("03_gungbok_byunghwa.md", "북방 수운이 오히려 흉하다", "#42"),
    ("09_gungbok_imsu.md", "해월은 **무토 → 병화 → 경금(갑목 제어)**", "#34 ③"),
    ("10_gungbok_gyesu.md", "- 화일간: 병화는 임수 → 경금, 정화는 오월만 임수가 먼저이고 사·미월은 갑목이 먼저", "#36 ⑦"),
    ("10_gungbok_gyesu.md", "- 토일간: 무토는 사월 갑목·오월 임수·미월 계수가 먼저, 기토는 계수 → 병화", "#36 ⑦"),
    ("10_gungbok_gyesu.md", "- 금일간: 경금은 사·오월 임수(미월은 정화·갑목), 신금은 임수(오월은 기토가 먼저)", "#36 ⑦"),
    ("10_gungbok_gyesu.md", "- 화일간: 정화는 갑목으로 연료(경금이 쪼갠다), 병화는 임수가 주(해월만 갑목이 먼저)", "#34 ⑧"),
    ("10_gungbok_gyesu.md", "- 토일간: 병화로 온기, 갑목이 다음(무토 해월은 갑목이 먼저, 기토 해월은 무토도 쓴다)", "#34 ⑧"),
    ("10_gungbok_gyesu.md", "- 금일간: 경금은 정화로 제련(축월은 병화가 먼저), 신금은 임수로 씻고 병화로 온기(축월은 병화가 먼저)", "#34 ⑧"),
    ("10_gungbok_gyesu.md", "**여름 공통**: 대개 수기(水氣)가 절실하다 — 다만 1순위는 일간과 달마다 다르다", "#36 ⑦"),
    ("10_gungbok_gyesu.md", "임수(壬, 겁재) → 계수(癸, 비견", "#46"),
    ("10_gungbok_gyesu.md", "**임수(壬水) 겁재·계수(癸水) 비견**", "#46"),
    ("10_gungbok_gyesu.md", "임수(겁재), 계수(비견), 경금", "#46"),
    ("09_gungbok_imsu.md", "그래서 취용 순서는 무토 → 병화 → 경금이다", "#29 ②"),
    ("04_gungbok_junghwa.md", "원문 칠월 단락(삼추 총론과 같은 문장)은 「七月丁火，退气柔弱，端用甲木」", "#32 ③"),
    ("04_gungbok_junghwa.md", "8월에는 갑목·병화·경금을 모두 쓴다고만 하고 우열은 매기지 않는다", "#32 ③"),
    ("07_gungbok_gyunggeum.md", "인월은 병화로 한기를 풀고 갑목으로 소토, 정화는 그다음", "#32 ①"),
    ("01_gungbok_gapmok.md", "해월도 같고(「丙火次之」), 축월은 十二月 단락에 병화가 없어 경금·정화만 쓴다", "#43"),
    ("01_gungbok_gapmok.md", "병화는 해·자월의 보조다(축월은 병화 없이 庚丁)", "#43"),
    ("01_gungbok_gapmok.md", "계수를 쓰는 달은 인월(「得丙癸逢」)과 술월(자양)이고, 진월·술월에는 임수도 취용에 든다", "#43"),
    ("04_gungbok_junghwa.md", "그 밖의 달에도 대개 갑목과 경금을 짝으로 쓴다(오월은 壬庚癸로 갑목이 없고, 미월은 甲壬으로 경금이 없다)", "#43"),
    ("07_gungbok_gyunggeum.md", "병화를 보좌로 쓰고(묘·사·유·해·자월 보좌)", "#43"),
    ("07_gungbok_gyunggeum.md", "- 원문 묘월: 경금이 당령한 을목을 만나면 반드시 을목에 정을 보내(「见庚必输情于乙」)", "#43"),
    ("07_gungbok_gyunggeum.md", "원문은 경금이 당령한 을목을 만나면 반드시 을목에 정을 보내 합(乙庚合)하므로(「见庚必输情于乙」)", "#43"),
    ("07_gungbok_gyunggeum.md", "정화는 그다음 3순위로(「丁火次之」), 무토는 화가 많을 때만(「如火多则用土」) 쓴다", "#43"),
    ("09_gungbok_imsu.md", "| 인월 | 초봄, 수생목 설기 | 경금, 병화(보좌) | 무토(비겁 왕할 때) |", "#43"),
    ("09_gungbok_imsu.md", "| 진월 | 늦봄, 무토 사령 | 갑목, 경금 | 계수(갑목 자양), 병화(수왕 시) |", "#44"),
    ("09_gungbok_imsu.md", "| 미월 | 늦여름, 기토 당권 | 신금, 갑목 | 계수, 임수 |", "#44"),
    ("02_gungbok_eulmok.md", "병화는 해·자월의 보조(축월은 병화 없이 庚丁, 해월 임수 범람 시 무토)", "#44"),
    ("03_gungbok_byunghwa.md", "1·2·7월엔 임수가 많을 때의 제방, 자월엔 임수의 보좌, 해월엔 갑·경과 함께", "#44"),
] + [(f, p, "#32 ④") for f in JOHU_FILES for p in ("| 미월 | 늦여름,", "**계절**: 늦여름")]     # 미월 매트릭스 계절 칸과 미월 절 계절 줄 — 「한여름」으로 되돌리면 실패
# errata로 바로잡은 그 달 '원문' 줄 인용 — 줄에서 빼면 실패한다. --johu로 다시 만들어도 풀리지 않는다
WONMUN_PINNED = {("丁", "亥"): ("三冬丁火，甲木为尊，庚金佐之", "#32 ③·#34 ⑤"),
                 ("庚", "巳"): ("次取戊土，丙火佐之", "#34 ⑤"),
                 ("辛", "寅"): ("先己后壬。己为君，庚为佐", "#36 ①")}
# 취용 글자가 그 달 '원문' 줄 인용에 글자로 나오지 않는 달
COVER_EXEMPT = {("癸", "未"): "壬", }         # 「宜比劫助身」의 比劫으로만 나온다 (10번 미월 상황 분석)
# 그 달 단락이 원문에 없어 계절 단락 전체에서 인용을 찾는 달 — md에 공통 단락임을 밝혀 두었다
SEASON_WIDE = {("乙", "丑"): "원문에 十二月乙木 단락이 없다",
               ("丁", "丑"): "三冬 결론 문장이 十一月丁火 단락 끝에 있다",
               ("丁", "亥"): "三冬 결론 문장(「三冬丁火，甲木为尊，庚金佐之」)이 十一月丁火 단락 끝에 있다"}


def _stems(cell, keep_paren=True):
    """칸 → 천간 목록. 천간 이름(병화)·한자(丙·丙火)·복합 약칭(무기토·병정·임계수)·오행 이름(화·화토·金)을 읽는다.
    keep_paren=False면 괄호 속 조건은 뺀다."""
    cell = NO_STEM.sub(" ", GLOSS.sub(r"\1", cell))
    cell = re.sub("(" + HZ + ")[木火土金水]", r"\1", cell)     # 癸水·丙火의 오행 글자는 앞 천간의 일부다
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


MONTH_HEAD_RE = re.compile(r"^### .*?[(（]([子丑寅卯辰巳午未申酉戌亥])月生[)）·,，\s]", re.M)    # (正月生)·(閏月生) 같은 머리는 월별 절이 아니다. (寅月生·正月生)·(寅月生, 正月)·（寅月生）도 읽는다


def _month_sections(txt):
    """{월지: 절 본문}. 같은 달 머리가 두 번 있으면 첫 절을 쓴다 — 중복은 check_johu가 따로 알린다."""
    heads = list(MONTH_HEAD_RE.finditer(txt))
    out = {}
    for i, h in enumerate(heads):
        out.setdefault(h.group(1), txt[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(txt)])
    return out


def _bullets(sec, title):
    """제목 아래 목록 줄. '* '·'+ '·'1. ' 목록도 '- '로 읽는다 — 다른 기호로 쓴 줄이 검사에서 빠지지 않게."""
    m = re.search(r"^\*\*" + re.escape(title) + r"\*\*\s*\n(.*?)(?=^\*\*|^---|\Z)", sec, re.M | re.S)
    if not m:
        return None
    return [l for l in (re.sub(r"^(?:[*+]|\d+[.)])\s+", "- ", l) for l in m.group(1).splitlines()) if l.startswith("- ")]


def _bullet_stems(lines):
    """굵은 이름 목록 → 천간. 굵은 글씨가 닫히지 않은 줄은 건너뛴다(check_johu가 따로 알린다)."""
    return [s_ for l in lines for m in [re.match(r"- \*\*(.+?)\*\*", l)] if m for s_ in _stems(m.group(1), keep_paren=False)]


def _months_of(marker):
    """원문 단락 머리 正二月甲木 → 인월 기준 달 번호 {0, 1}. 十一二月은 동짓달·섣달. 앞의 总之·故는 건너뛴다."""
    m = re.match(r"(?:总之[，,]?|故)?((?:十一|十二|十|正|二|三|四|五|六|七|八|九)+)月", marker)
    if not m:
        return set()
    if m.group(1) == "十一二":
        return {10, 11}
    return {MONTH_NO[t] for t in re.findall("十一|十二|十|正|二|三|四|五|六|七|八|九", m.group(1))}


def source_blocks():
    """(천간, 지지) → (계절 단락 전체, 그 달 인용이 있어야 할 글 = 계절 머리말 + 그 달을 덮는 단락, 그 달 단락만).
    굵은 머리 없이 줄 첫머리에 N月+일간(总之·故 포함)으로 시작하는 줄도 그 달 단락 머리로 본다 — 甲 三夏 五六月甲木, 戊 三春 三月戊土, 壬 三秋 七~九月 등.
    달 숫자 없는 굵은 머리(三秋甲木)는 계절 머리말처럼 석 달 모두의 allowed에 넣는다."""
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
            season = re.sub(r"(?m)^((?:总之[，,]?|故)?(?:十一|十二|十|正|二|三|四|五|六|七|八|九)+月" + g + ")", BOLD + r"\1" + BOLD, season)
            parts = re.split("(" + BOLD + "[^']+" + BOLD + ")", season)
            for k in range(3):
                mi = si * 3 + k
                z = S.MONTH_ZHI[mi]
                js = [j for j in range(1, len(parts), 2) if mi in _months_of(parts[j].strip("'"))]
                gen = [j for j in range(1, len(parts), 2) if not _months_of(parts[j].strip("'"))]
                # 「或'''八月'''一派辛金…」처럼 或·若로 여는 단락은 특수 조건이라 그 달 단락(own)으로 치지 않고, allowed에는 或·若를 붙여 둔다
                cond = {j: parts[j - 1].rstrip()[-1] if parts[j - 1].rstrip().endswith(("或", "若")) else "" for j in js + gen}
                paras = "".join(cond[j] + parts[j] + parts[j + 1] for j in sorted(js + gen))
                own = season if (g, z) in SEASON_WIDE else "".join(parts[j] + parts[j + 1] for j in js if not cond[j])
                allowed = season if (g, z) in SEASON_WIDE else parts[0] + paras
                out[g, z] = (season.replace(BOLD, ""), allowed.replace(BOLD, ""), own.replace(BOLD, ""))
    return out


def _kept_sentences(q):
    """순위를 읽을 문장 — 或·若·凡·如 조건문과 支成·支会 문장은 뺀다."""
    return [s_ for s_ in re.split(r"(?<=。)", q) if s_.strip() and not COND.match(s_) and not re.search("支成|支会", s_)]


def _negated(text):
    """꺼리는 말(NEG·NEG_USE) 속 천간."""
    return {c for m in NEG.finditer(text) for c in m.group(1)} | {c for m in NEG_USE.finditer(text) for grp in m.groups() if grp for c in grp if c in STEMS}


def _head_stems(s_, g, keep_g=False):
    """문장의 으뜸 말 글자 차례 — 꺼리는 말 속 글자는 빼고, keep_g가 아니면 일간도 뺀다(专取壬水比肩의 壬은 일간이 1순위인 달)."""
    spans = [m.span() for m in NEG.finditer(s_)] + [m.span() for m in NEG_USE.finditer(s_)]
    out = []
    for m in HEADW.finditer(s_):
        k = next(i for i in range(1, len(m.groups()) + 1) if m.group(i))
        if (keep_g or m.group(k) != g) and not any(a <= m.start(k) < b for a, b in spans):
            out.append(m.group(k))
    return out


def _rank_problems(g, z, q, order, is_json=False):
    """인용·원문 문장의 순위 말 ↔ order. 어긋나면 그 까닭을 돌려준다 — RANK_EXEMPT의 글자 쌍만 뺀다.
    ① 쌍(PAIR)·뒤(FOLLOW)·약한 뒤(WEAK)·바로 다음(HEAD_NEXT)의 앞뒤, ② 순위 말이 매긴 글자(꺼리는 말 속 글자 빼고)가 order에 있는가,
    ③ 不可专用X의 X와 次·佐로 둔 글자가 1순위가 아닌가, ④ 첫 으뜸 말 글자가 1순위인가(일간도 센다 — 专取壬水比肩). 조건문은 읽지 않는다."""
    out, o = [], "".join(order)
    sents = _kept_sentences(q)
    text = "".join(sents)
    neg = _negated(text)
    ranked = set()
    for m in NAMED.finditer(text):
        for s_ in filter(None, m.groups()):
            if s_ != g and s_ not in order and s_ not in neg:
                out.append((None, f"인용이 순위를 매긴 {s_}(「{m.group(0)}」)이 취용 순서 {o}에 없다"))
    heads = []                               # 앞 문장들의 으뜸 글자 — 다음 문장의 次·佐는 이들보다 뒤
    for s_ in sents:
        sneg = _negated(s_)
        for m in PAIR.finditer(s_):
            gs = m.groups()
            a, b = (gs[7], gs[6]) if gs[6] else next((gs[k], gs[k + 1]) for k in (0, 2, 4, 8) if gs[k])
            ranked |= {a, b}
            if a in order and b in order and order.index(a) > order.index(b):
                out.append(({a, b}, f"「{m.group(0)}」는 {a}가 {b}보다 앞인데 취용 순서는 {o}"))
        for m, strong in [(m, True) for m in FOLLOW.finditer(s_)] + [(m, False) for m in WEAK.finditer(s_)]:
            ys = [c for c in (m.group(1) or m.group(2) or m.group(3)) if c in STEMS]
            lead = []
            if m.group(1) and len(ys) > 1 and re.search(r"(?:后|次)(?:用|取|看)?$", s_[: m.start(1)]):
                lead = ys[:1]                  # 先癸后丁庚金次之 — 丁은 后의 글자라 庚보다 앞이다
                ys = ys[1:]
            if strong:
                ranked |= set(ys)
                if order and order[0] != g and order[0] in ys:
                    out.append(({order[0]}, f"「{m.group(0)}」는 {order[0]}를 보좌(次·佐)로 두는데 취용 1순위다"))
            xs = [c for c in dict.fromkeys(s_[: m.start()] + "".join(lead)) if c in order and c not in ys and c != g and c not in sneg]
            xs += [h for h in heads if strong and h not in xs and h not in ys]
            for y in ys:
                for x in xs:
                    if y in order and order.index(x) > order.index(y):
                        out.append(({x, y}, f"「{m.group(0)}」는 {y}가 {x} 뒤인데 취용 순서는 {o}"))
        for x in _head_stems(s_, g):
            ranked.add(x)
            if x in order and x not in heads:
                heads.append(x)
        for m in HEAD_NEXT.finditer(s_):
            x, y = m.groups()
            if x in order and (y not in order or order.index(y) != order.index(x) + 1):
                out.append(({x, y}, f"「{m.group(0)}」는 {y}가 {x} 바로 다음인데 취용 순서는 {o}"))
        for m in NOT_FIRST.finditer(s_):
            if order and order[0] == m.group(1):
                out.append(({m.group(1)}, f"「{m.group(0)}」인데 {m.group(1)}이 취용 1순위다"))
    for s_ in sorted(ranked - set(order) - {g} - neg):
        out.append((None, f"순위 말이 매긴 {s_}이 취용 순서 {o}에 없다"))
    hs = next((h for h in map(lambda t: _head_stems(t, g, keep_g=True), sents) if h), [])    # 첫 으뜸 말은 1순위 — 일간이 1순위인 달도 본다
    if hs and order and hs[0] != order[0] and (hs[0] != g or g in order):
        out.append(({hs[0], order[0]}, f"{'json 인용' if is_json else '인용·원문 문장'}의 첫 으뜸 말이 {hs[0]}인데 취용 1순위는 {order[0]}"))
    pairs, json_ok, _why = RANK_EXEMPT.get((g, z), (set(), False, ""))
    exempt = pairs if json_ok or not is_json else set()
    return [msg for pair, msg in out if pair is None or frozenset(pair) not in exempt]


def _month_sentences(z, text):
    """그 달을 덮는 N月(总之·故 N月)이나 그 계절 이름(三秋甲木)으로 시작하는 원문 문장 — 或·若·凡 조건문과 支成·支会 문장은 뺀다."""
    i = S.MONTH_ZHI.index(z)
    for s_ in re.split(r"(?<=。)|\n", text):
        s_ = s_.strip()
        m = LEAD.match(s_)
        sm = re.match(r"(?:总之[，,]?|故)?(三春|三夏|三秋|三冬)", s_)
        if (m and i in _months_of(m.group(0)) or sm and SEASONS.index(sm.group(1)) == i // 3) \
                and not re.match("或|若|凡", s_) and not re.search("支成|支会", s_):
            ex = re.search(r"(?:惟|唯|独)(" + MK.pattern + ")", s_) if sm else None    # 三秋乙木…先丙后癸，惟九月耑用癸水 — 九月은 뒤쪽만, 나머지 달은 앞쪽만
            yield s_ if not ex else s_[ex.start():] if i in _months_of(ex.group(1)) else s_[: ex.start()]


def _simile(seg, mm):
    """비유·견줌 속 달 이름 — 如七八月之间旱, 与五月一理. 그 달 문장이라는 표시가 아니다."""
    pre, post = seg[max(0, mm.start() - 1): mm.start()], seg[mm.end(): mm.end() + 2]
    return pre in ("与", "同", "似", "犹") or post == "一理" or (pre == "如" and post == "之间")


def _in_order(q, text):
    """인용 q가 text에 있는가 — 「A…B」처럼 줄임표로 덜어 낸 인용은 조각들이 차례대로 있으면 된다."""
    k = 0
    for part in (p for p in re.split(r"…|\.\.\.", q) if p):          # ASCII '...'도 줄임표로 본다
        k = text.find(part, k)
        if k < 0:
            return False
        k += len(part)
    return True


def _anchor_problems(z, q, allowed):
    """인용이 그 달 자리에서 시작하는가 — 달 숫자 중간·다른 달 첫머리·다른 달 표시 뒤에서 자른 인용을 잡는다."""
    out, i, k = [], S.MONTH_ZHI.index(z), allowed.find(q)
    if k < 0 and _in_order(q, allowed):              # 줄임표로 덜어 낸 인용은 첫 조각 자리에서 본다
        k = allowed.find(next(p for p in re.split(r"…|\.\.\.", q) if p))
    lead = re.match(r"(?:总之[，,]?|[或若如凡])?" + MK.pattern, q)       # 或五月乏癸 — 인용이 제 달을 밝히고 시작한다
    if k > 0 and allowed[k - 1] in NUM and re.match("[" + NUM + "]*月", q):
        out.append(f"인용이 원문의 달 숫자 중간에서 시작한다(「{allowed[k - 1]}{q[:6]}…」)")
    if k > 0 and allowed[k - 1] in "或若如凡":
        out.append(f"인용이 원문의 조건 말 {allowed[k - 1]} 바로 뒤에서 시작한다(「{allowed[k - 1]}{q[:6]}…」) — {allowed[k - 1]}까지 인용할 것")
    if lead and i not in _months_of(lead.group(1) + "月"):
        out.append(f"인용 첫머리 {lead.group(1)}月이 {MON_HEAD[z]}이 아니다")
    if k >= 0 and not lead:
        seg = allowed[allowed.rfind(chr(10), 0, k) + 1: k]
        prev = [mm for mm in MK.finditer(seg) if not _simile(seg, mm)]
        head = LEAD.match(seg)
        if prev and i not in _months_of(prev[-1].group(0)):
            joint = head and i in _months_of(head.group(0)) and _months_of(prev[-1].group(0)) <= _months_of(head.group(0))
            if not (joint and seg[prev[-1].end():].count("。") >= 2):    # 五六月 단락의 「六月…」은 그 문장과 다음 문장까지만 六月이다
                out.append(f"인용 바로 앞의 달 표시가 {prev[-1].group(0)}이다 — 다른 달 문장")
    return out


KO_MONTH = dict(zip("인묘진사오미신유술해자축", S.MONTH_ZHI))
KO_MONTH_NO = {"정": 0, "이": 1, "삼": 2, "사": 3, "오": 4, "육": 5, "칠": 6, "팔": 7, "구": 8, "십": 9, "십일": 10, "십이": 11, "동짓": 10, "섣": 11}
KO_STEM = "갑목|을목|병화|정화|무토|기토|경금|신금|임수|계수"
GLOSS_ITEM = r"[갑을병정무기경신임계]\(" + HZ + r"[^)]*\)"                      # 무(戊) — 한 글자 이름에 한자를 단 것
STEM_ITEM = r"(?:(?:" + KO_STEM + r")(?:\([^)]*\))?|" + GLOSS_ITEM + "|" + HZ + HE + ")"
CHAIN_ITEM = r"(?:[가-힣]{2}(?:\([^)]*\))?|" + GLOSS_ITEM + "|" + HZ + HE + ")"
CHAIN = re.compile(CHAIN_ITEM + r"(?:\s*→\s*" + CHAIN_ITEM + ")+")
ARROW_ALT = re.compile(r"\s*(?:⇒|->|=>|—>|–>|⟶|⟹|➔|➜|➡|⇨|→)\s*")              # 다른 화살표도 →로 읽는다
ARROW_GT = re.compile("(" + STEM_ITEM + r")\s*>\s*(?=" + STEM_ITEM + ")")         # 천간 사이의 > 도 →
ARROW_BACK = re.compile(STEM_ITEM + r"\s*(?:<-|<|←|⟵)\s*" + STEM_ITEM)            # 거꾸로 화살표 — 순서를 거꾸로 읽게 되니 쓰지 않는다
SOON = re.compile(r"(" + STEM_ITEM + r"(?:\s*[·,，、]\s*" + STEM_ITEM + r")+)\s*(?:의\s*)?순(?=으로|이다|이며|[^가-힣]|$)")   # 무토·경금·병화 순 ('甲·癸 순서에서'는 순서를 말하지 않는다)
RANK_SEQ = re.compile(r"([1-4])순위\s*(?:는|은|가|이|:)?\s*(" + STEM_ITEM + ")")       # 1순위 무토, 2순위 경금
RANK_AFTER = re.compile("(" + STEM_ITEM + r")\s*(?:—\s*|\(\s*)([1-4])순위(?!\s*" + STEM_ITEM + ")")    # 경금(3순위)·경금 — 3순위 (— 1순위 정화를 …는 RANK_SEQ)
RANK_SUBJ = re.compile(r"(?:^-?\s*|[,，.。;；:：]\s*)(" + KO_STEM + r")(?:\([^)]*\))?[은는][^,，.。;；]*?\(([1-4])순위\)")   # 경금은 …대용(3순위)
PAIR_MD = re.compile(r"先(?:用|取|看)?(" + HZ + ")" + HE + r"(?:後|后|次)(?:用|取|看)?(" + HZ + ")|(" + HZ + ")" + HE + "先(" + HZ + ")" + HE + "(?:後|后)")
MON_RUN = re.compile(r"(?:(?:[인묘진사오미신유술해자축]·)*[인묘진사오미신유술해자축]월|(?:십일|십이|[정이삼사오육칠팔구십])+월)[은는]\s*((?:" + HZ + "){2,4})(?![木火土金水]|" + HZ + ")")   # 해월은 庚丁
KO_FIRST = re.compile("(" + STEM_ITEM + r")[을를이가]\s*먼저[^,，。.;；]*?[,，]\s*(" + STEM_ITEM + r")[을를이가은는]\s*(?:나중|다음|그다음|뒤)")
KO_MONTHS = re.compile(r"((?:[인묘진사오미신유술해자축]·)*[인묘진사오미신유술해자축])월|((?:십일|십이|[정이삼사오육칠팔구십])+)월|(동짓|섣)달|(?<![\d·])(\d+(?:·\d+)*)월")
SEASON_KO = {"봄": "寅卯辰", "여름": "巳午未", "가을": "申酉戌", "겨울": "亥子丑"}
SEASON_HEAD = re.compile(r"^(?:- )?(봄|여름|가을|겨울)(?:\s*\(([인묘진사오미신유술해자축·]+)\))?\s*(?:[:：]|공통)")
# 마디 첫머리의 'X는'·'X 일간은'·'X에게는'·'X의 경우'·'X(乙)은'·'乙木은' — 다른 일간 이야기
STEM_SUBJ = re.compile(r"(?:(?:^-?\s*|[,，.。;；:：|]\s*)(" + KO_STEM + "|" + HZ + r"[木火土金水])(?:\([^)]*\))?\s*(?:일간\s*)?(?:은|는|에게는|에겐|의 경우|일 때는?)(?![가-힣])"
                       r"|(?<![가-힣])(" + KO_STEM + r")의(?=\s*(?:[인묘진사오미신유술해자축]·?)+월))")    # 마디 첫머리 주어, 또는 어디서든 '갑목의 진월'
# 조건·반론 마디의 사슬은 그 달 취용 순서가 아니다 — '…하면', '…때', 다른 해석을 소개하는 말
CHAIN_SKIP = re.compile(r"[가-힣]면(?![가-힣])|때(?![가-힣])|해석|견해|학파|현대|일부|흔히|잘못|오류|폐기|아니라|支会|支成|[若或如凡]")
GEN = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
ELEM = {c: e for e, cs in zip("木火土金水", ["甲乙", "丙丁", "戊己", "庚辛", "壬癸"]) for c in cs}


def _ko_months(m):
    """'사·오월'·'정이월'·'동짓달'·'4·5월'(음력 순서, 1월=인월) → 지지 목록."""
    if m.group(1):
        return [KO_MONTH[c] for c in m.group(1).split("·")]
    if m.group(2):
        return [S.MONTH_ZHI[KO_MONTH_NO[t]] for t in re.findall("십일|십이|[정이삼사오육칠팔구십]", m.group(2))]
    if m.group(3):
        return [S.MONTH_ZHI[KO_MONTH_NO[m.group(3)]]]
    return [S.MONTH_ZHI[(int(t) - 1) % 12] for t in m.group(4).split("·")]


def _months_in(text):
    return [z for mm in KO_MONTHS.finditer(text) for z in _ko_months(mm)]


def _item_stem(p_):
    return (_stems(p_, keep_paren=False) or ["?"])[0]


def _table_cells(line):
    """표 줄 → [(칸 시작, 칸 끝)]."""
    bars = [i for i, c in enumerate(line) if c == "|"]
    return list(zip(bars, bars[1:]))


def _chains(txt, g):
    """01~10 본문에서 취용 순서를 말하는 곳 → (줄 번호, 천간, 지지 목록, 원문 조각, 천간 차례, 종류).
    종류: 'chain' — 'A → B → C' 사슬과 'A·B·C 순'(앞머리부터 차례대로 고른 글자여야 한다), 'pair' — 先X後Y·X先Y後·'X를 먼저, Y를 나중에'(앞뒤만 본다),
    'rank' — 'N순위 X'·'X(N순위)'·'X는 …(N순위)'(천간 차례에 순위 번호를 단다: [(N, X)]).
    천간은 사슬 앞의 'X는·X 일간은·X에게는·X의 경우' 같은 주어, 표 칸이면 그 열 머리의 일간, 없으면 그 파일의 일간이다.
    달은 ① 사슬 앞 마디(쉼표·마침표 뒤, 쌍점은 끊지 않는다)의 달 이름 → ② 사슬 바로 뒤 괄호가 달 이름뿐이면 그 달 → ③ 그 줄이 든 X월생 절의 달 →
    ④ 그 줄이나 단락 머리의 계절(봄·여름·가을·겨울, '(사·오·미)')에서, 같은 천간 마디 안에 따로 이름이 나온 달을 뺀 달이다. 못 정하면 지지 목록이 비어 있다.
    굵은 글씨는 지우고, ⇒·->·⟶·➔ 같은 화살표와 천간 사이의 >는 →로 읽는다(거꾸로 화살표는 'back'으로 따로 낸다).
    양력 달 표기, 코드 블록, '원문 (窮通寶鑑)'·'원문 취용 순서' 줄(따로 검사), 「」 속 원문, 조건·반론 마디(CHAIN_SKIP)는 읽지 않는다.
    상생 흐름(경금 → 임수 → 갑목 → 병화처럼 일간까지 이어지는 오행 흐름)은 취용 순서가 아니다."""
    sec, block, code, head = None, None, False, None
    for ln, raw in enumerate(txt.splitlines(), 1):
        if raw.startswith("```"):
            code = not code
        if code or raw.startswith(("**원문 취용 순서**", "**원문 (窮通寶鑑)**")):
            continue
        if raw.startswith("#"):
            mh = MONTH_HEAD_RE.match(raw)
            sec, block = (mh.group(1) if mh else None), None
            continue
        if not raw.strip():
            block = head = None
            continue
        line = re.sub(r"양력\s*[\d·~]+월", "", raw.replace("**", ""))
        line = re.sub(r"「[^」]*」|\"[^\"]*[一-鿿][^\"]*\"", lambda m: "＿" * len(m.group(0)), line)    # 원문 인용(「」·\"…\")은 따로 검사 — 자리만 남긴다
        line = ARROW_ALT.sub(" → ", line)
        line = ARROW_GT.sub(r"\1 → ", line)
        is_row = line.lstrip().startswith("|")
        cells = _table_cells(line) if is_row else []
        if is_row and not head:                     # 표 머리줄 — 열마다 일간 이름이 있으면 그 열의 천간
            head = [next((KO[n] for n in re.findall(KO_STEM, line[a:b])), None) or
                    next((c for c in re.findall(HZ + "(?=[木火土金水])", line[a:b])), None) for a, b in cells]
            continue
        sh = SEASON_HEAD.match(line)
        if sh:
            block = [KO_MONTH[c] for c in sh.group(2) if c != "·"] if sh.group(2) else list(SEASON_KO[sh.group(1)])
        subj = [(m.start(k), KO.get(m.group(k), m.group(k)[0])) for m in STEM_SUBJ.finditer(line) for k in (1, 2) if m.group(k)]

        def where(a, b, after_text=""):
            """[a, b) 조각 → (천간, 지지 목록, 마디)."""
            op = line.rfind("(", 0, a)
            if op >= 0 and ")" not in line[op: a]:      # 괄호 속이면 괄호 앞 마디까지 — 「…이루면 …(支成土局，先甲后丁)」
                clause = re.split(r"[,，。.;；|]", line[: op])[-1] + line[op: a]
                inner = re.split(r"[,，。.;；|]", line[op: a])[-1]
                if _months_in(inner):                  # 괄호 속에 달 이름이 있으면 그 달 — '10월 목왕 시 (정월은 …)'
                    clause = inner
            else:
                clause = re.split(r"[,，。.;；|]", line[: a])[-1]
            before = [s_ for s_ in subj if s_[0] < a]
            col = next((k for k, (x, y) in enumerate(cells) if x < a < y), None)
            col_stem = head[col] if head and col is not None and col < len(head) else None
            cell_a = cells[col][0] if col is not None else 0
            if before and before[-1][0] >= cell_a:
                stem, seg_a = before[-1][1], before[-1][0]
            else:
                stem, seg_a = col_stem or (before[-1][1] if before and not is_row else g), (cell_a if col is not None else (before[-1][0] if before else 0))
            seg_b = next((s_[0] for s_ in subj if s_[0] > b), cells[col][1] if col is not None else len(line))
            zs = _months_in(clause)
            if not zs and after_text and _months_in(after_text) and not re.sub(KO_MONTHS.pattern + r"|[,·\s]", "", after_text):
                zs = _months_in(after_text)
            if not zs and sec:
                zs = [sec]
            if not zs and block:
                named = set(_months_in(line[seg_a: seg_b]))
                zs = [z for z in block if z not in named]
            return stem, zs, clause

        for m in ARROW_BACK.finditer(line):
            yield ln, g, [], m.group(0), [], "back"
        found = [(ch.start(), ch.end(), ch.group(0), re.split(r"\s*→\s*", ch.group(0))) for ch in CHAIN.finditer(line)]
        found += [(m.start(), m.end(), m.group(0), re.split(r"\s*[·,，、]\s*", m.group(1))) for m in SOON.finditer(line)]
        found += [(m.start(1), m.end(), m.group(0), list(m.group(1))) for m in MON_RUN.finditer(line)]
        for a, b, text, parts in found:
            if not all(re.fullmatch("(?:" + KO_STEM + ")|" + HZ + HE + "|" + GLOSS_ITEM, re.sub(r"\((?!" + HZ + r")[^)]*\)", "", p_).strip()) for p_ in parts):
                continue
            after = re.search(r"\(([^)]*)\)$", parts[-1]) or re.match(r"\s*\(([^)]*)\)", line[b:])    # 마지막 항목에 붙은 괄호나 사슬 뒤 괄호
            stem, zs, clause = where(a, b, after.group(1) if after else "")
            if CHAIN_SKIP.search(clause):
                continue
            stems = [_item_stem(p_) for p_ in parts]
            if len(stems) >= 3 and stem in stems and all(GEN[ELEM.get(x, "木")] == ELEM.get(y) for x, y in zip(stems, stems[1:])):
                continue                            # 상생 흐름
            yield ln, stem, zs, text, stems, "chain"
        pairs = [(m.start(), m.end(), m.group(0), (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))) for m in PAIR_MD.finditer(line)]
        pairs += [(m.start(), m.end(), m.group(0), (_item_stem(m.group(1)), _item_stem(m.group(2)))) for m in KO_FIRST.finditer(line)]
        for a, b, text, xy in pairs:
            stem, zs, clause = where(a, b)
            if not CHAIN_SKIP.search(clause):
                yield ln, stem, zs, text, list(xy), "pair"
        if is_row:
            continue                                # 표 칸의 순위 숫자(12개월 중 10개월 1순위)는 달별 순위가 아니다
        ranks = []
        for m in RANK_SEQ.finditer(line):               # '1순위 무토, 2순위 경금, 3순위 병화'는 한 묶음 — 첫 항목의 달로 읽는다
            if ranks and re.fullmatch(r"\s*[,，、]\s*", line[ranks[-1][1]: m.start()]):
                ranks[-1] = (ranks[-1][0], m.end(), line[ranks[-1][0]: m.end()], ranks[-1][3] + [(int(m.group(1)), _item_stem(m.group(2)))])
            else:
                ranks.append((m.start(), m.end(), m.group(0), [(int(m.group(1)), _item_stem(m.group(2)))]))
        ranks += [(m.start(), m.end(), m.group(0), [(int(m.group(2)), _item_stem(m.group(1)))]) for m in RANK_AFTER.finditer(line)]
        ranks += [(m.start(1), m.end(), m.group(0), [(int(m.group(2)), KO[m.group(1)])]) for m in RANK_SUBJ.finditer(line)]
        for a, b, text, nx in ranks:
            stem, zs, clause = where(a, b)
            if not CHAIN_SKIP.search(clause) and (sec or _months_in(clause)):
                yield ln, stem, zs, text, nx, "rank"


def check_johu():
    with open(os.path.join(ROOT, SRC), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != SRC_SHA256:
            problems.append(f"{SRC}: 원문 사본이 고정 해시(SRC_SHA256)와 다르다 — 원문을 다시 받았다면 해시와 함께 고치고 errata에 적을 것")
    table = json.loads(read("references/johu_wonmun.json"))["table"]
    src = source_blocks()
    for g, name in zip(S.GAN, JOHU_FILES):
        txt = read("references/" + name)
        secs = _month_sections(txt)
        if sorted(secs) != sorted(S.MONTH_ZHI):
            miss = "·".join(MON_HEAD[z] for z in S.MONTH_ZHI if z not in secs)
            problems.append(f"{name}: 월별 절(### X월생(…月生)) 12개를 찾지 못했다 ({len(secs)}개 — {miss} 없음. 그 달 본문 검사는 건너뛴다)")
        heads = [h.group(1) for h in MONTH_HEAD_RE.finditer(txt)]
        for z in dict.fromkeys(z for z in heads if heads.count(z) > 1):
            problems.append(f"{name}: 「({z}月生)」 머리가 {heads.count(z)}번 있다 — (…月生)은 월별 절 머리에만 쓴다(사례·비교 절은 다른 제목으로)")
        rows = re.findall(r"^\| (" + "|".join(MON) + r") \|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", txt, re.M)[:12]
        if [MON[r[0]] for r in rows] != list(S.MONTH_ZHI):
            problems.append(f"{name}: 조후 매트릭스 12행(인월~축월 순)을 찾지 못했다 ({len(rows)}행)")
        for m, season, yong, hui, gi in rows:
            z = MON[m]
            order = table[g][z]["order"]
            if not season.strip().startswith(SEASON_CELL[S.MONTH_ZHI.index(z)]):
                notes.append(f"{name} {m}: 매트릭스 계절 칸 '{season.strip()}'이 '{SEASON_CELL[S.MONTH_ZHI.index(z)]}'로 시작하지 않는다 (errata #32 ④)")
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
            if z not in secs:                              # 절을 못 찾은 달은 위의 한 줄로 알린다 — 뒤따르는 검사는 군소리다
                continue
            sec = secs[z]
            by, bh, bg = (_bullets(sec, t) for t in ("용신 (用神)", "희신 (喜神)", "기신 (忌神)"))
            if by is None or bh is None or bg is None:
                problems.append(f"{name} {m}: 본문에 용신·희신·기신 목록이 없다")
                continue
            for l in by + bh + bg:
                if l.startswith("- **") and not re.match(r"- \*\*(.+?)\*\*", l):
                    problems.append(f"{name} {m}: 목록 줄의 굵은 이름이 닫히지 않았다 — {l[:30]}")
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
                b = re.match(r"- \*\*(.+?)[:：]?\*\*(?: [^—–:：\n]{1,12}?)?\s*(?:—|–|-|:|：)\s*([1-4](?:·[1-4])*)순위", l)   # '**계수** 비견 — 4순위'·'**병화**: 3순위'·' - 3순위'도 읽는다
                if b:
                    want = [order.index(s_) + 1 if s_ in order else None for s_ in _stems(b.group(1), keep_paren=False)]
                    if want != [int(x) for x in b.group(2).split("·")]:
                        problems.append(f"{name} {m}: '{b.group(1)}' {b.group(2)}순위 ≠ 원문 취용 순서상 {want}")
        for z in S.MONTH_ZHI:
            q, order = table[g][z]["quote"], table[g][z]["order"]
            plain, allowed, own = src[g, z]
            season = SEASONS[S.MONTH_ZHI.index(z) // 3]
            if q not in allowed:
                problems.append(f"{name} {MON_HEAD[z]}: json 인용이 원문 그 달 단락(또는 {season} 머리말)에 없다 — {q[:20]}…")
            if order[0] != g and order[0] not in q:
                problems.append(f"{name} {MON_HEAD[z]}: json 인용에 원문 1순위 {order[0]}이 없다 — 취용 근거 문장을 인용할 것")
            lead = LEAD.match(q)
            if own.strip() and q not in own and not (lead and S.MONTH_ZHI.index(z) in _months_of(lead.group(0))) and (g, z) not in PREFACE_OK:
                problems.append(f"{name} {MON_HEAD[z]}: 그 달 단락이 있는데 json 인용이 {season} 머리말 문장이다 — 그 달 단락에서 인용할 것")
            for s_ in order:
                if s_ != g and s_ not in EXAM.sub(" ", plain):
                    problems.append(f"{name} {MON_HEAD[z]}: 취용 {s_}이 원문 {season}{g} 단락에 한 번도 나오지 않는다")
            if z not in secs:
                continue
            sec = secs[z]
            for label, pat in [("'원문' 인용 줄", r"^\*\*(?:원문|原文)(?! 취용 순서)[^\n]*「"), ("'원문 취용 순서' 줄", r"^\*\*원문 취용 순서\*\*")]:    # **원문**:·**원문 보충**:·**원문 (보충)**: 「…」도 센다
                n_ = len(re.findall(pat, sec, re.M))
                if n_ > 1:                                 # 검사는 첫 줄만 읽으므로 둘째 줄은 받지 않는다
                    problems.append(f"{name} {MON_HEAD[z]}: {label}이 {n_}개다 — 그 달에 한 줄만 쓴다(둘째 줄은 검사하지 않는다)")
            wl = re.search(r"^\*\*원문 \(窮通寶鑑\)\*\*: (.+)$", sec, re.M)
            if not wl or f"「{q}」" not in wl.group(1):
                problems.append(f"{name} {MON_HEAD[z]}: johu_wonmun.json 원문 인용이 그 달 '원문' 줄에 그대로 없다")
            qms = list(re.finditer(r"(조건\s*)?「([^」]+)」", wl.group(1) if wl else ""))
            quotes = [m_.group(2) for m_ in qms]
            ranked_q = [m_.group(2) for m_ in qms if not m_.group(1)]     # '조건 「…」'으로 적은 조건문은 순위로 읽지 않는다
            if wl and wl.group(1).count("「") != wl.group(1).count("」"):
                problems.append(f"{name} {MON_HEAD[z]}: '원문' 줄의 「」가 짝이 맞지 않는다 — '원문' 줄은 한 줄로 쓴다(줄을 바꾸면 뒷줄은 읽지 않는다)")
            if wl and not re.match(r"\s*\n\*\*원문 취용 순서\*\*", sec[wl.end():]):    # 두 줄 사이에 끼운 줄은 검사하지 않으므로 받지 않는다
                problems.append(f"{name} {MON_HEAD[z]}: '원문 취용 순서' 줄이 '원문' 줄 바로 다음 줄이 아니다 — 두 줄 사이에 다른 줄을 두지 않는다")
            if wl:                                        # '원문' 줄 아래 이어 쓴 인용은 읽지 않으므로 받지 않는다
                rest = sec[wl.end():]
                stop = re.search(r"^(?:\*\*|#|---|\|)", rest, re.M)
                if "「" in rest[: stop.start() if stop else len(rest)]:
                    problems.append(f"{name} {MON_HEAD[z]}: '원문' 줄 아래 줄에 「」 인용이 이어진다 — '원문' 줄은 한 줄로 쓴다(뒷줄 인용은 검사하지 않는다)")
            if (g, z) in WONMUN_PINNED and WONMUN_PINNED[g, z][0] not in "　".join(quotes):
                problems.append(f"{name} {MON_HEAD[z]}: errata {WONMUN_PINNED[g, z][1]}로 넣은 인용 「{WONMUN_PINNED[g, z][0]}」이 '원문' 줄에 없다")
            for qq in quotes:
                if not _in_order(qq, allowed):
                    problems.append(f"{name} {MON_HEAD[z]}: '원문' 줄 인용 「{qq[:20]}…」이 원문 그 달 단락에 없다")
            # 인용 자리·순위 말은 json 인용과 '원문' 줄 인용 모두, 그리고 그 달 N月로 시작하는 원문 문장에서 본다
            whys = [w for qq in dict.fromkeys([q] + quotes) for w in _anchor_problems(z, qq, allowed)
                    + (_rank_problems(g, z, qq, order, qq == q) if qq == q or qq in ranked_q else [])]
            whys += ["원문 문장 — " + w for s_ in _month_sentences(z, allowed) for w in _rank_problems(g, z, s_, order)]
            for why in dict.fromkeys(whys):
                problems.append(f"{name} {MON_HEAD[z]}: {why}")
            cited = EXAM.sub(" ", NEG_USE.sub(" ", "　".join(quotes)))
            for s_ in order:
                if s_ != g and s_ not in cited and COVER_EXEMPT.get((g, z)) != s_:
                    problems.append(f"{name} {MON_HEAD[z]}: 취용 {s_}의 근거가 '원문' 줄 인용에 없다 (꺼리는 말 속 글자는 근거가 아니다)")
            if (g, z) in RANK_EXEMPT_NOTE and RANK_EXEMPT_NOTE[g, z] not in sec:
                problems.append(f"{name} {MON_HEAD[z]}: RANK_EXEMPT의 근거 문장 「{RANK_EXEMPT_NOTE[g, z]}」이 그 달 절에 없다")
            ol = re.search(r"^\*\*원문 취용 순서\*\*: (.+)$", sec, re.M)
            got = None
            if not ol:
                problems.append(f"{name} {MON_HEAD[z]}: '**원문 취용 순서**: …' 줄을 찾지 못했다 (굵은 이름 뒤에 ': ')")
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
                    m2 = re.match(r"\s*(?:\*\*)?([가-힣]{2})(?:\*\*)?\s*[(（]([甲乙丙丁戊己庚辛壬癸])", part)     # **신금(辛)**·**신금**(辛)·신금 (辛)·신금（辛）도 읽는다
                    m3 = m2 or re.match(r"\s*(?:\*\*)?([甲乙丙丁戊己庚辛壬癸])(?:\*\*)?\s*[(（]([가-힣]{2})", part)    # 庚(경금)
                    ko, hz = (m2.group(1), m2.group(2)) if m2 else ((m3.group(2), m3.group(1)) if m3 else (None, None))
                    if not hz:
                        problems.append(f"{name} {MON_HEAD[z]}: '원문 취용 순서' 항목 '{part.strip()}'에 한자 표기(예: 병화(丙))가 없다")
                    elif KO.get(ko) != hz:                   # 읽는 사람은 한글 이름을 본다 — 한자와 어긋나면 순서가 거꾸로 읽힌다
                        problems.append(f"{name} {MON_HEAD[z]}: '원문 취용 순서' 항목 '{part.strip()}'의 이름 {ko}와 한자 {hz}가 맞지 않는다")
                    got.append(hz or "?")
            if ol and got != order:
                problems.append(f"{name} {MON_HEAD[z]}: '원문 취용 순서' {''.join(got or [])} ≠ json order {''.join(order)}")
        # 본문·요약의 순서 말은 원문 취용 순서와 맞아야 한다 — 산문은 규칙으로 다 읽을 수 없어 '확인 권장'으로만 낸다(errata #40).
        # 되돌림은 01~10 본문 고정(tests/fixtures/johu_docs.json, test_johu_docs_pinned)이 잡는다
        for ln, stem, zs, chain, stems, kind in _chains(txt, g):
            if kind == "back":
                notes.append(f"{name} {ln}행: 「{chain}」 — 거꾸로 화살표(<·←)는 쓰지 않는다. 취용 순서는 → 로 적을 것")
                continue
            if not zs and kind != "rank":
                notes.append(f"{name} {ln}행: 「{chain}」의 달을 정할 수 없다 — 앞에 달 이름을 적을 것")
            for z in zs:
                order = table[stem][z]["order"]
                if kind == "rank":
                    bad = [(n, x) for n, x in stems if x != stem and (x not in order or order.index(x) + 1 != n)]
                    if bad:
                        notes.append(f"{name} {ln}행 {MON_HEAD[z]}({stem}): 「{chain}」 — {bad[0][1]}은 원문 취용 순서 {''.join(order)}"
                                     + (f"에서 {order.index(bad[0][1]) + 1}순위" if bad[0][1] in order else "에 없다"))
                    continue
                idx = [order.index(s_) if s_ in order else None for s_ in stems]
                if None in idx or idx != sorted(idx) or (kind == "chain" and stems[0] not in (order[0], stem)):
                    notes.append(f"{name} {ln}행 {MON_HEAD[z]}({stem}): 「{chain}」 ≠ 원문 취용 순서 {''.join(order)}")


def check_errata_pins():
    for f, phrase, no in ERRATA_PINNED:
        if phrase not in read("references/" + f):
            problems.append(f"{f}: errata {no}로 고친 문장 「{phrase}」이 없다 — 되돌렸다면 errata와 함께 ERRATA_PINNED도 고칠 것")
    if sorted(RANK_EXEMPT) != sorted(RANK_EXEMPT_NOTE):
        problems.append("RANK_EXEMPT와 RANK_EXEMPT_NOTE의 달이 다르다")


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
    if B.BEGIN not in html or B.END not in html:
        problems.append("web/unui-sigantable.html에 GENERATED:TABLES 구획 표시가 없다 — 표시 줄을 되돌리고 python3 scripts/build_web_tables.py")
        return
    a, b = html.index(B.BEGIN), html.index(B.END) + len(B.END)
    if html[a:b] != B.block():
        problems.append("web/unui-sigantable.html 표 구획이 saju_calc.py와 다르다 — python3 scripts/build_web_tables.py")


def main():
    def check_doc_tables():
        check_tables([os.path.join(ROOT, "SKILL.md"), os.path.join(ROOT, "github-linked", "SKILL.md"),
                      os.path.join(ROOT, "README.md")] + sorted(glob.glob(os.path.join(REF, "*.md"))))
    checks = [check_janggan_doc, check_corpus_notes, check_shinsal_doc, check_samhyeong, check_johu, check_errata_pins,
              check_doc_tables, check_paths] + ([] if "--skip-web" in sys.argv else [check_web])
    for fn in checks:
        try:
            fn()
        except Exception as e:                        # 문서를 고치다 검사기가 멈추면 다른 검사 결과까지 가려진다 — 문제로 적고 계속한다
            problems.append(f"검사기 오류({getattr(fn, '__name__', '?')}): {type(e).__name__}: {e} — 이 검사의 나머지 결과는 빠졌다. 문서 형식을 확인할 것")
    if notes:
        print(f"확인 권장 {len(notes)}건 (실패로 치지 않는다 — 본문 산문의 순서 표기·계절 칸 낱말은 규칙으로 다 읽을 수 없다. 원문과 직접 대조할 것)")
        for n_ in notes:
            print(" ·", n_)
    if problems:
        print(f"일치 검사 실패 {len(problems)}건")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("일치 검사 통과")


if __name__ == "__main__":
    main()
