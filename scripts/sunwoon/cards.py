#!/usr/bin/env python3
"""
cards.py — 선운의 명리터 영상 카드 검사·작업 목록 (LLM 호출 0)

  python3 scripts/sunwoon/cards.py lint [ID ...]      # 카드 검사 (인자 없으면 전부). 문제가 있으면 종료 코드 1
  python3 scripts/sunwoon/cards.py todo [--batch 10]  # 자막은 있는데 카드가 없는 편, 오래된 순으로 묶음 출력(JSON)

카드 형식 (research/sunwoon/cards/<id>.md):

  ---
  id: <videoId>
  title: <영상 제목>
  date: YYYY-MM-DD          # index.csv published와 같아야 한다
  kind: video|short|live
  tags: [지장간, 십성]       # research/sunwoon/taxonomy.md 안에서만
  ---
  ## 요지                    # 내 말로 3~7줄 (- 로 시작)
  ## 주장                    # 1. 주장 … @m:ss  (번호 목록, 줄마다 출처 시각 1개 이상)
  ## 사례                    # 명조는 간지만. 없으면 '- 없음'
  ## 저장소 대조             # - NN …: 일치|보강|충돌|신규 — 한 줄   (references 번호, SKILL, 없음)

저작권 계약 — 자막 문장을 옮기지 않는다:
  - 「」·“”·"" 인용은 공백 뺀 20자 이하
  - 카드 본문에서 공백을 뺀 21자 연속 구간이 자막(공백 뺀)에 그대로 있으면 실패 (로컬 캐시가 있을 때)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as C  # noqa: E402

CARDS = C.ROOT / "research" / "sunwoon" / "cards"
TAXONOMY = C.ROOT / "research" / "sunwoon" / "taxonomy.md"
SECTIONS = ["요지", "주장", "사례", "저장소 대조"]
KINDS = {"video", "short", "live"}
QUOTE_MAX = 20
VERBATIM_WINDOW = QUOTE_MAX + 1  # 허용 인용(20자)보다 한 자라도 길게 겹치면 복제로 본다
VERDICTS = ("일치", "보강", "충돌", "신규")

_TS = re.compile(r"@(\d{1,2}):(\d{2})(?::(\d{2}))?")
_QUOTE = re.compile(r"「([^」]*)」|“([^”]*)”|\"([^\"]*)\"")
_REF = re.compile(r"^-\s*(\d{2}|SKILL|없음)\b")


def load_tags(path: Path = TAXONOMY) -> set[str]:
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", path.read_text(encoding="utf-8"), re.M))


def parse_card(text: str) -> tuple[dict[str, str], dict[str, list[str]], str]:
    """(frontmatter, 절 이름 → 내용 줄들, 본문 전체). 형식이 깨지면 ValueError."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("frontmatter(---) 없음")
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    body = m.group(2)
    secs: dict[str, list[str]] = {}
    cur = None
    order: list[str] = []
    for line in body.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            cur = h.group(1)
            order.append(cur)
            secs[cur] = []
        elif cur is not None and line.strip():
            secs[cur].append(line.strip())
    secs["__order__"] = order
    return fm, secs, body


def ts_seconds(m: re.Match) -> int:
    a, b, c = m.groups()
    return int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def verbatim_hits(body: str, transcript: str, window: int = VERBATIM_WINDOW) -> list[str]:
    """카드 본문에서 자막과 공백 무시 window자 이상 겹치는 구간들 (시각 표지·출처 표기는 빼고 본다)."""
    tr = _squash(re.sub(r"\[\d+:\d{2}(?::\d{2})?\]", "", transcript))
    hits: list[str] = []
    for line in body.splitlines():
        s = _squash(_TS.sub("", line))
        i = 0
        while i + window <= len(s):
            if s[i:i + window] in tr:
                hits.append(s[i:i + window])
                i += window
            else:
                i += 1
    return hits


def lint_card(path: Path, index: dict[str, dict[str, str]], tags: set[str],
              cache: Path = C.CACHE) -> list[str]:
    errs: list[str] = []
    vid = path.stem
    try:
        fm, secs, body = parse_card(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{vid}: {exc}"]
    row = index.get(vid)
    if row is None:
        errs.append(f"{vid}: index.csv에 없는 id")
    if fm.get("id") != vid:
        errs.append(f"{vid}: frontmatter id({fm.get('id')})가 파일 이름과 다르다")
    if row and fm.get("date") != row["published"]:
        errs.append(f"{vid}: date {fm.get('date')} ≠ index {row['published']}")
    if fm.get("kind") not in KINDS:
        errs.append(f"{vid}: kind는 video|short|live")
    got = [t.strip() for t in fm.get("tags", "").strip("[]").split(",") if t.strip()]
    if not got:
        errs.append(f"{vid}: tags 비었음")
    bad = [t for t in got if t not in tags]
    if bad:
        errs.append(f"{vid}: taxonomy 밖 태그 {bad}")
    if secs["__order__"] != SECTIONS:
        errs.append(f"{vid}: 절 순서는 {SECTIONS} (지금 {secs['__order__']})")
        return errs
    gist = [l for l in secs["요지"] if l.startswith("-")]
    if not 3 <= len(gist) <= 7:
        errs.append(f"{vid}: 요지는 3~7줄 (지금 {len(gist)})")
    claims = [l for l in secs["주장"] if re.match(r"^\d+\.", l)]
    if not claims:
        errs.append(f"{vid}: 주장 번호 목록 없음")
    limit = int(row["duration"]) + 30 if row and row.get("duration", "").isdigit() else None
    for l in claims:
        stamps = list(_TS.finditer(l))
        if not stamps:
            errs.append(f"{vid}: 출처 시각(@m:ss) 없는 주장 — {l[:30]}")
        elif limit and any(ts_seconds(s) > limit for s in stamps):
            errs.append(f"{vid}: 영상 길이를 넘는 시각 — {l[:30]}")
    if not secs["사례"]:
        errs.append(f"{vid}: 사례 절이 비었음 (없으면 '- 없음')")
    refs = secs["저장소 대조"]
    if not refs:
        errs.append(f"{vid}: 저장소 대조 절이 비었음")
    for l in refs:
        if not _REF.match(l) or not (l.startswith("- 없음") or any(v in l for v in VERDICTS)):
            errs.append(f"{vid}: 대조 줄 형식 '- NN …: 일치|보강|충돌|신규' — {l[:30]}")
    for m in _QUOTE.finditer(body):
        q = next(g for g in m.groups() if g is not None)
        if len(_squash(q)) > QUOTE_MAX:
            errs.append(f"{vid}: 인용이 {QUOTE_MAX}자를 넘는다 — {q[:20]}…")
    tr = cache / f"{vid}.txt"
    if tr.exists():
        for h in verbatim_hits(body, tr.read_text(encoding="utf-8"))[:3]:
            errs.append(f"{vid}: 자막 문장을 그대로 옮겼다 — {h}")
    return errs


def todo(index: dict[str, dict[str, str]], cards: Path = CARDS, batch: int = 10) -> list[list[str]]:
    ready = sorted((r for r in index.values() if r["status"] == "fetched" and not (cards / f"{r['id']}.md").exists()),
                   key=lambda r: (r["published"] or "9999", r["id"]))
    ids = [r["id"] for r in ready]
    return [ids[i:i + batch] for i in range(0, len(ids), batch)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="선운 영상 카드 검사")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("lint")
    lp.add_argument("ids", nargs="*")
    tp = sub.add_parser("todo")
    tp.add_argument("--batch", type=int, default=10)
    a = ap.parse_args(argv)
    index = C.load_index()
    if a.cmd == "todo":
        print(json.dumps(todo(index, batch=a.batch), ensure_ascii=False))
        return 0
    tags = load_tags()
    paths = [CARDS / f"{i}.md" for i in a.ids] if a.ids else sorted(CARDS.glob("*.md"))
    errs: list[str] = []
    for p in paths:
        errs += [f"{p.stem}: 파일 없음"] if not p.exists() else lint_card(p, index, tags)
    for e in errs:
        print(e)
    print(f"카드 {len(paths)}장, 문제 {len(errs)}건")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
