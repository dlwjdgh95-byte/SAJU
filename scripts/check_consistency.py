#!/usr/bin/env python3
"""
check_consistency.py — 문서와 코드가 같은 표를 쓰는지, 문서 구조가 깨지지 않았는지 검사한다.

  python3 scripts/check_consistency.py      # 문제가 있으면 목록을 출력하고 종료 코드 1

검사 항목
  1. 장간표: references/26 §2-2 ↔ saju_calc.JANGGAN (지장간가)
  2. 원전 코퍼스 주석: references/24의 '장간 …' 주석 ↔ saju_calc
  3. 십이운성 정본표: references/30 §2-2 ↔ saju_calc.unseong()
  4. 신살 조견표: references/30 §3-1·3-2 ↔ saju_calc 표
  5. 삼형 명칭: references/22 ↔ saju_calc.SAMHYEONG
  6. 조후 용신: references/01~10 월별 원문 줄·취용 순서 줄·매트릭스·본문 용신 목록 ↔ references/johu_wonmun.json
  7. 마크다운 표 깨짐 (빈 줄로 끊긴 표 등)
  8. SKILL.md·github-linked/SKILL.md가 가리키는 파일의 존재
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
    head = rows[0][1:]
    for r in rows[1:]:
        z = r[0]
        for col, val in zip(head, r[1:]):
            for g in col.split("·"):
                if S.unseong(g, z) != val:
                    problems.append(f"30 §2-2 십이운성 {g}{z}: 문서 {val} ≠ 코드 {S.unseong(g, z)}")
    rows = table_rows(section(t, r"^### 3-1\."))
    names = {"양인": S.YANGIN, "문창귀인": S.MUNCHANG, "학당귀인": S.HAKDANG, "금여": S.GEUMYEO, "홍염살": S.HONGYEOM}
    head = rows[0][1:11]
    for r in rows[1:]:
        key = next((k for k in names if k in r[0]), None)
        if not key:
            continue
        for g, val in zip(head, r[1:11]):
            want = names[key].get(g, "—")
            if val != want:
                problems.append(f"30 §3-1 {key} {g}: 문서 {val} ≠ 코드 {want}")
    m = re.search(r"\*\*천을귀인.*?\*\* — (.+)", t)
    if m:
        for part in m.group(1).split(" / "):
            gs, zs = part.split(" → ")
            for g in gs.split("·"):
                if set(zs.replace("·", "")) != set(S.CHEONEUL[g.strip()]):
                    problems.append(f"30 천을귀인 {g}: 문서 {zs} ≠ 코드 {S.CHEONEUL[g.strip()]}")
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
def check_samhyeong():
    t = read("references/22_hapchung_shinsal.md")
    for chars, name in S.SAMHYEONG.items():
        short = name.split("(")[0]
        if not re.search(f"{chars}[^\\n]{{0,40}}{short}|{short}[^\\n]{{0,40}}{chars}", t):
            problems.append(f"22번에 '{chars} = {short}' 명시가 없다 (errata #12)")


# 6 ─ 조후 용신
KO = {"갑목": "甲", "을목": "乙", "병화": "丙", "정화": "丁", "무토": "戊", "기토": "己",
      "경금": "庚", "신금": "辛", "임수": "壬", "계수": "癸"}
EL = {"목": "甲乙", "화": "丙丁", "토": "戊己", "금": "庚辛", "수": "壬癸",
      "木": "甲乙", "火": "丙丁", "土": "戊己", "金": "庚辛", "水": "壬癸"}
MON = dict(zip(["인월", "묘월", "진월", "사월", "오월", "미월", "신월", "유월", "술월", "해월", "자월", "축월"], S.MONTH_ZHI))
MON_HEAD = dict(zip(S.MONTH_ZHI, ["인월", "묘월", "진월", "사월", "오월", "미월", "신월", "유월", "술월", "해월", "자월", "축월"]))


def _stems(cell, keep_paren=True):
    """칸 → 천간 목록. 한글 이름(병화)과 한자(丙)를 모두 읽는다. keep_paren=False면 괄호 속 조건은 뺀다."""
    if not keep_paren:
        cell = re.sub(r"\([^)]*\)", "", cell)
    return [KO.get(k, k) for k in re.findall("|".join(KO) + "|[甲乙丙丁戊己庚辛壬癸]", cell)]


def _elements(part):
    """기신 칸 조각 → 오행 이름만으로 적은 글자들 ('화', '화(火)', '火'). 갑목·병화 같은 천간 이름 안의 글자는 세지 않는다."""
    rest = re.sub("|".join(KO), "", part)
    return "".join(EL[e] for e in re.findall(r"(?<![가-힣])[목화토금수](?![가-힣])|[木火土金水]", rest))


def _month_sections(txt):
    heads = list(re.finditer(r"^### .*?\((.)月生\)", txt, re.M))
    return {h.group(1): txt[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(txt)]
            for i, h in enumerate(heads)}


def _bullet_stems(sec, title):
    m = re.search(r"^\*\*" + re.escape(title) + r"\*\*\s*\n(.*?)(?=^\*\*|^---|\Z)", sec, re.M | re.S)
    if not m:
        return None
    return [s_ for l in m.group(1).splitlines() if l.startswith("- **")
            for s_ in _stems(re.match(r"- \*\*(.+?)\*\*", l).group(1))]


def check_johu():
    table = json.loads(read("references/johu_wonmun.json"))["table"]
    files = sorted(glob.glob(os.path.join(REF, "0[1-9]_gungbok_*.md"))) + sorted(glob.glob(os.path.join(REF, "10_gungbok_*.md")))
    for g, f in zip(S.GAN, files):
        txt = open(f, encoding="utf-8").read()
        name = os.path.basename(f)
        secs = _month_sections(txt)
        if sorted(secs) != sorted(S.MONTH_ZHI):
            problems.append(f"{name}: 월별 절(### X월생(…月生)) 12개를 찾지 못했다 ({len(secs)}개)")
        rows = re.findall(r"^\| (" + "|".join(MON) + r") \|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", txt, re.M)[:12]
        if len(rows) != 12:
            problems.append(f"{name}: 조후 매트릭스 12행을 찾지 못했다 ({len(rows)}행)")
        for m, _season, yong, hui, gi in rows:
            z = MON[m]
            order = table[g][z]["order"]
            ys, hs = _stems(yong), _stems(hui)
            if order[0] not in ys:
                problems.append(f"{name} {m}: 원문 1순위 {order[0]}이 용신 칸에 없다")
            for s_ in order:
                if s_ not in ys + hs and s_ != g:
                    problems.append(f"{name} {m}: 원문 취용 {s_}이 용신·희신 칸에 없다")
            for s_ in _stems(yong, keep_paren=False):
                if s_ not in order:
                    problems.append(f"{name} {m}: 용신 칸 {s_}이 원문 취용 순서({''.join(order)})에 없다")
            for part in [p.strip() for p in re.split(r"[,，]", gi)]:
                qualified = "과다" in part or "추가" in part
                if qualified:
                    continue
                subject = re.sub(r"\([^)]*\)", "", part)          # 괄호는 이유(丁壬合 등) — 기신 글자는 괄호 밖이다
                for s_ in _stems(subject) + list(_elements(subject)):
                    if s_ in order:
                        problems.append(f"{name} {m}: 기신 칸 '{part}'에 원문 용신 {s_} ('과다'·'추가' 조건 없음)")
                        break
            sec = secs.get(z, "")
            by, bh = _bullet_stems(sec, "용신 (用神)"), _bullet_stems(sec, "희신 (喜神)")
            if by is None or bh is None:
                problems.append(f"{name} {m}: 본문에 용신·희신 목록이 없다")
            else:
                if set(by) != set(_stems(yong, keep_paren=False)):
                    problems.append(f"{name} {m}: 본문 용신 {''.join(by)} ≠ 매트릭스 용신 {''.join(_stems(yong, keep_paren=False))}")
                if not set(_stems(hui, keep_paren=False)) <= set(bh) | {g}:
                    problems.append(f"{name} {m}: 매트릭스 희신 {''.join(_stems(hui, keep_paren=False))}가 본문 희신 {''.join(bh)}에 없다")
        for z in S.MONTH_ZHI:
            q, order = table[g][z]["quote"], table[g][z]["order"]
            sec = secs.get(z, "")
            wl = re.search(r"^\*\*원문 \(窮通寶鑑\)\*\*: (.+)$", sec, re.M)
            if not wl or f"「{q}」" not in wl.group(1):
                problems.append(f"{name} {MON_HEAD[z]}: johu_wonmun.json 원문 인용이 그 달 '원문' 줄에 그대로 없다")
            ol = re.search(r"^\*\*원문 취용 순서\*\*: (.+)$", sec, re.M)
            got = re.findall(r"[가-힣]{2}\(([甲乙丙丁戊己庚辛壬癸])", ol.group(1)) if ol else None
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
def check_paths():
    for doc in ["SKILL.md", "github-linked/SKILL.md", "README.md"]:
        for ref in sorted(set(re.findall(r"(?:references|scripts|tests|web)/[\w./-]+\.(?:md|py|json|html|mjs)", read(doc)))):
            if not os.path.exists(os.path.join(ROOT, ref)):
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
