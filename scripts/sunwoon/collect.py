#!/usr/bin/env python3
"""
collect.py — 유튜브 「선운의 명리터」 전 영상 인벤토리·자막 수집 (LLM 호출 0, 재개 가능)

  python3 scripts/sunwoon/collect.py list              # 영상·쇼츠·라이브 탭 전수 → research/sunwoon/index.csv
  python3 scripts/sunwoon/collect.py new               # RSS 최신 15편 중 index에 없는 편만 추가
  python3 scripts/sunwoon/collect.py fetch --workers 6 # status가 fetched가 아닌 편의 자막 수집
  python3 scripts/sunwoon/collect.py pull [ID ...]     # R2 → 로컬 캐시 (카드 작성 전, 컨테이너가 새로 떴을 때)
  python3 scripts/sunwoon/collect.py status            # 상태별 편수

저작권 계약: 이 저장소는 공개다. 자막 전문은 git에 넣지 않는다.
  - 로컬 캐시 .cache/sunwoon/<id>.txt (.gitignore)
  - 비공개 R2 버킷(R2_ACCOUNT_ID·R2_ACCESS_KEY_ID·R2_SECRET_ACCESS_KEY, WIKI_R2_BUCKET 기본 miner-wiki-raw)
    키 saju/sunwoon/transcripts/<id>.txt — 공개 URL을 만들지 않고 GET도 서명한다
  index.csv에는 메타데이터(제목·날짜·길이·자막 종류·글자 수·sha256)만 남긴다.

자막 텍스트는 약 30초 단위 줄로, 줄마다 [m:ss] 또는 [h:mm:ss] 표지를 붙인다 — 카드의 주장 출처(@m:ss)가 이 표지를 가리킨다.

클라우드 IP는 로그인 없이 공개 영상도 봇 확인에 막힌다 — YOUTUBE_COOKIES_B64 또는 YOUTUBE_COOKIES_FILE 필요.
병렬은 스레드 풀 하나다. 같은 IP·같은 쿠키라 동시 요청을 크게 늘리면 차단되므로 기본 6, 봇 확인·429가 오면 백오프한다.

출처: Miner 레포 invest-wiki/scripts/collect_youtube.py(트랙 선택·쿠키 해석·yt-dlp 옵션)와
r2store.py(SigV4 private 버킷)에서 필요한 부분만 옮겼다. 자막 파서는 시각 표지를 보존하도록 새로 썼다.
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "research" / "sunwoon" / "index.csv"
CACHE = ROOT / ".cache" / "sunwoon"

CHANNEL_ID = "UCHaJ6PG2TI6V3a3VilQ9HvQ"
CHANNEL_URL = f"https://www.youtube.com/channel/{CHANNEL_ID}"
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
WATCH_URL = "https://www.youtube.com/watch?v={}"
TABS = (("videos", "video"), ("shorts", "short"), ("streams", "live"))

FIELDS = ["id", "title", "published", "duration", "kind", "caption", "chars", "sha256", "status"]
KST = dt.timezone(dt.timedelta(hours=9))
BUCKET_SEC = 30
LANG_ORDER = ("ko", "ko-orig")  # 수동 자막은 ko 계열 아무거나, 자동은 ko → ko-orig
BLOCK_MARKS = ("confirm you", "429", "Too Many Requests", "rate-limit")


# ── index.csv ────────────────────────────────────────────────────────────
def load_index(path: Path = INDEX) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["id"]: {k: r.get(k, "") for k in FIELDS} for r in csv.DictReader(f)}


def save_index(rows: dict[str, dict[str, str]], path: Path = INDEX) -> None:
    """날짜 오름차순(날짜 모르는 편은 뒤), 같은 날은 id 순. 임시 파일에 쓰고 바꿔 끼운다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    order = sorted(rows.values(), key=lambda r: (r["published"] or "9999", r["id"]))
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in order:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(path)


def merge_listing(rows: dict[str, dict[str, str]], entries: list[dict[str, Any]], kind: str) -> int:
    """탭 나열 결과를 index에 합친다. 이미 있는 편은 제목만 갱신하고 상태는 건드리지 않는다. 새 편 수를 돌려준다."""
    added = 0
    for e in entries:
        vid = e.get("id")
        if not vid:
            continue
        title = " ".join(str(e.get("title") or "").split())
        if vid in rows:
            rows[vid]["title"] = title or rows[vid]["title"]
            continue
        dur = e.get("duration")
        rows[vid] = {"id": vid, "title": title, "published": "", "duration": str(int(dur)) if dur else "",
                     "kind": kind, "caption": "", "chars": "", "sha256": "", "status": "pending"}
        added += 1
    return added


# ── 자막 트랙·파서 ────────────────────────────────────────────────────────
def pick_track(info: dict[str, Any]) -> dict[str, str] | None:
    """수동 자막(ko 계열)이 자동 자막보다 우선. 형식은 json3 → vtt 순. {url, ext, lang, kind} 또는 None."""
    for kind, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        tracks = info.get(key) or {}
        for lang in LANG_ORDER:
            cands = [lang] if lang in tracks else []
            if kind == "manual" and not cands:
                cands = [k for k in tracks if k.split("-")[0] == "ko"]
            for k in cands:
                fmts = tracks.get(k) or []
                fmt = next((f for e in ("json3", "vtt") for f in fmts if f.get("ext") == e), None)
                if fmt:
                    return {"url": fmt["url"], "ext": fmt["ext"], "lang": k, "kind": kind}
    return None


def fmt_ts(sec: float) -> str:
    s = int(sec)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _bucket(cues: list[tuple[float, str]], size: int = BUCKET_SEC) -> str:
    """(시작 초, 문장) 목록 → 줄마다 '[m:ss] 문장들'. 같은 문장이 이어지면(자동 자막의 줄 넘김) 한 번만 둔다."""
    out: list[str] = []
    cur_start: float | None = None
    cur: list[str] = []
    last = ""
    for start, text in cues:
        text = " ".join(text.split())
        if not text or text == last:
            continue
        last = text
        if cur_start is None or start - cur_start >= size:
            if cur:
                out.append(f"[{fmt_ts(cur_start)}] " + " ".join(cur))
            cur_start, cur = start, []
        cur.append(text)
    if cur:
        out.append(f"[{fmt_ts(cur_start)}] " + " ".join(cur))
    return "\n".join(out)


def json3_to_timed(payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    cues = []
    for ev in data.get("events") or []:
        text = "".join(seg.get("utf8", "") for seg in ev.get("segs") or [])
        if text.strip():
            cues.append((ev.get("tStartMs", 0) / 1000.0, text))
    return _bucket(cues)


_VTT_TIME = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})\s*-->")
_VTT_TAG = re.compile(r"<[^>]+>")


def vtt_to_timed(vtt: str) -> str:
    cues: list[tuple[float, str]] = []
    start: float | None = None
    for line in vtt.splitlines():
        line = line.strip()
        m = _VTT_TIME.match(line)
        if m:
            h, mi, s, ms = m.groups()
            start = int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000
            continue
        if not line:
            start = None
            continue
        if start is None:
            continue  # 머리말·NOTE·큐 번호
        text = _VTT_TAG.sub("", line).strip()
        if text:
            cues.append((start, text))
    return _bucket(cues)


def parse_timed(payload: str, ext: str) -> str:
    return json3_to_timed(payload) if ext == "json3" else vtt_to_timed(payload)


def published_kst(info: dict[str, Any]) -> str:
    ts = info.get("release_timestamp") or info.get("timestamp")
    if ts:
        return dt.datetime.fromtimestamp(int(ts), tz=KST).strftime("%Y-%m-%d")
    raw = str(info.get("upload_date") or "")
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 else ""


# ── R2 private 버킷 (Miner r2store.py에서 옮김) ───────────────────────────
def transcript_key(vid: str) -> str:
    return f"saju/sunwoon/transcripts/{vid}.txt"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


class R2Store:
    def __init__(self, account_id: str, access_key: str, secret_key: str, bucket: str, timeout: int = 30):
        self.access_key, self.secret_key, self.bucket, self.timeout = access_key, secret_key, bucket, timeout
        self.host = f"{account_id}.r2.cloudflarestorage.com"

    @classmethod
    def from_env(cls) -> "R2Store | None":
        e = os.environ
        if not (e.get("R2_ACCOUNT_ID") and e.get("R2_ACCESS_KEY_ID") and e.get("R2_SECRET_ACCESS_KEY")):
            return None
        return cls(e["R2_ACCOUNT_ID"], e["R2_ACCESS_KEY_ID"], e["R2_SECRET_ACCESS_KEY"],
                   e.get("WIKI_R2_BUCKET") or "miner-wiki-raw")

    def _req(self, method: str, key: str, data: bytes = b"") -> urllib.request.Request:
        now = dt.datetime.now(dt.timezone.utc)
        amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        ph = hashlib.sha256(data).hexdigest()
        uri = f"/{self.bucket}/" + "/".join(urllib.parse.quote(s, safe="") for s in key.split("/"))
        hdr = {"host": self.host, "x-amz-content-sha256": ph, "x-amz-date": amz}
        if data:
            hdr["content-type"] = "text/plain; charset=utf-8"
        names = sorted(hdr)
        creq = "\n".join([method, uri, "", "".join(f"{n}:{hdr[n]}\n" for n in names), ";".join(names), ph])
        scope = f"{day}/auto/s3/aws4_request"
        sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(creq.encode()).hexdigest()])
        k = _hmac(_hmac(_hmac(_hmac(f"AWS4{self.secret_key}".encode(), day), "auto"), "s3"), "aws4_request")
        sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
        out = {n: v for n, v in hdr.items() if n != "host"}
        out["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                                f"SignedHeaders={';'.join(names)}, Signature={sig}")
        return urllib.request.Request(f"https://{self.host}{uri}", data=data or None, headers=out, method=method)

    def put(self, key: str, data: bytes) -> None:
        urllib.request.urlopen(self._req("PUT", key, data), timeout=self.timeout).read()

    def get(self, key: str) -> bytes:
        return urllib.request.urlopen(self._req("GET", key), timeout=self.timeout).read()

    def exists(self, key: str) -> bool:
        try:
            urllib.request.urlopen(self._req("HEAD", key), timeout=self.timeout).read()
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise


# ── yt-dlp (지연 import — 오프라인 테스트는 패키지가 없어도 돈다) ────────────
def resolve_cookies_file() -> str | None:
    if os.environ.get("YOUTUBE_COOKIES_FILE"):
        return os.environ["YOUTUBE_COOKIES_FILE"]
    b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if not b64:
        return None
    fd, tmp = tempfile.mkstemp(prefix="yt-cookies-", suffix=".txt")
    with os.fdopen(fd, "wb") as f:
        f.write(base64.b64decode(b64))
    return tmp


class YtClient:
    """스레드마다 YoutubeDL 인스턴스를 따로 둔다(인스턴스는 스레드 안전하지 않다)."""

    def __init__(self, cookiefile: str | None):
        import yt_dlp

        self._yt = yt_dlp
        self._opts: dict[str, Any] = {"quiet": True, "no_warnings": True, "noprogress": True,
                                      "skip_download": True, "ignore_no_formats_error": True}
        if cookiefile:
            self._opts["cookiefile"] = cookiefile
        self._local = threading.local()

    def _ydl(self):
        if not hasattr(self._local, "ydl"):
            self._local.ydl = self._yt.YoutubeDL(dict(self._opts))
        return self._local.ydl

    def list_tab(self, tab: str) -> list[dict[str, Any]]:
        with self._yt.YoutubeDL({**self._opts, "extract_flat": "in_playlist"}) as y:
            info = y.extract_info(f"{CHANNEL_URL}/{tab}", download=False)
        return list(info.get("entries") or [])

    def video_info(self, vid: str) -> dict[str, Any]:
        return self._ydl().extract_info(WATCH_URL.format(vid), download=False)

    def fetch(self, url: str) -> bytes:
        return self._ydl().urlopen(url).read()


# ── 수집 ─────────────────────────────────────────────────────────────────
def fetch_one(client: Any, store: Any, vid: str, cache: Path | None = None) -> dict[str, str]:
    """한 편: 메타데이터 → 트랙 → 시각 표지 텍스트 → 캐시·R2. index에 덮어쓸 필드를 돌려준다."""
    cache = cache or CACHE
    info = client.video_info(vid)
    upd = {"published": published_kst(info), "duration": str(int(info.get("duration") or 0) or "")}
    track = pick_track(info)
    if track is None:
        return {**upd, "caption": "none", "chars": "0", "sha256": "", "status": "no_caption"}
    text = parse_timed(client.fetch(track["url"]).decode("utf-8", "replace"), track["ext"])
    if not text:
        return {**upd, "caption": track["kind"], "chars": "0", "sha256": "", "status": "empty"}
    data = text.encode("utf-8")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{vid}.txt").write_bytes(data)
    if store is not None:
        store.put(transcript_key(vid), data)
    return {**upd, "caption": track["kind"], "chars": str(len(text)),
            "sha256": hashlib.sha256(data).hexdigest(), "status": "fetched" if store is not None else "cached"}


def is_block(exc: BaseException) -> bool:
    msg = str(exc)
    return any(m in msg for m in BLOCK_MARKS)


def fetch_all(rows: dict[str, dict[str, str]], client: Any, store: Any, *, workers: int = 6,
              limit: int | None = None, retries: int = 3, backoff: float = 20.0,
              save=save_index, sleep=time.sleep, log=print) -> dict[str, int]:
    """fetched가 아닌 편을 스레드 풀로 받는다. 봇 확인·429는 모든 스레드가 함께 쉬고(백오프 배수) 다시 시도한다.
    10편마다, 그리고 끝에 index를 저장한다(중간에 끊겨도 이어 받기)."""
    todo = [r["id"] for r in sorted(rows.values(), key=lambda r: r["id"]) if r["status"] != "fetched"]
    if limit:
        todo = todo[:limit]
    lock = threading.Lock()
    gate = threading.Event()
    gate.set()
    counts: dict[str, int] = {}
    done = [0]

    def work(vid: str) -> tuple[str, dict[str, str]]:
        for attempt in range(retries + 1):
            gate.wait()
            try:
                return vid, fetch_one(client, store, vid)
            except Exception as exc:  # noqa: BLE001 — 실패는 index에 사유로 남긴다
                if is_block(exc) and attempt < retries:
                    with lock:
                        if gate.is_set():
                            gate.clear()
                            wait = backoff * (3 ** attempt)
                            log(f"  ! 차단 신호({vid}) — {wait:.0f}초 쉰다")
                            sleep(wait)
                            gate.set()
                    continue
                return vid, {"status": "error:" + " ".join(str(exc).split())[:80].replace(",", " ")}
        return vid, {"status": "error:retries"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, v) for v in todo]):
            vid, upd = fut.result()
            with lock:
                rows[vid].update(upd)
                st = upd["status"].split(":")[0]
                counts[st] = counts.get(st, 0) + 1
                done[0] += 1
                if done[0] % 10 == 0:
                    save(rows)
                    log(f"  {done[0]}/{len(todo)} {counts}")
    save(rows)
    return counts


def rss_entries() -> list[dict[str, str]]:
    raw = urllib.request.urlopen(RSS_URL, timeout=30).read()
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    out = []
    for e in ET.fromstring(raw).findall("a:entry", ns):
        link = e.find("a:link", ns)
        kind = "short" if link is not None and "/shorts/" in (link.get("href") or "") else "video"
        out.append({"id": e.findtext("yt:videoId", "", ns), "title": e.findtext("a:title", "", ns), "kind": kind})
    return out


def pull(ids: list[str], rows: dict[str, dict[str, str]], store: Any, cache: Path = CACHE) -> int:
    """R2 → 캐시. ids가 비면 fetched인 편 전부. 이미 캐시에 있고 sha256이 맞으면 건너뛴다."""
    ids = ids or [r["id"] for r in rows.values() if r["status"] == "fetched"]
    cache.mkdir(parents=True, exist_ok=True)
    n = 0
    for vid in ids:
        p = cache / f"{vid}.txt"
        want = rows.get(vid, {}).get("sha256")
        if p.exists() and (not want or hashlib.sha256(p.read_bytes()).hexdigest() == want):
            continue
        p.write_bytes(store.get(transcript_key(vid)))
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="선운의 명리터 인벤토리·자막 수집")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("new")
    f = sub.add_parser("fetch")
    f.add_argument("--workers", type=int, default=6)
    f.add_argument("--limit", type=int)
    p = sub.add_parser("pull")
    p.add_argument("ids", nargs="*")
    sub.add_parser("status")
    a = ap.parse_args(argv)

    rows = load_index()
    if a.cmd == "status":
        c: dict[str, int] = {}
        for r in rows.values():
            c[r["status"]] = c.get(r["status"], 0) + 1
        print(f"{len(rows)}편", c)
        return 0
    if a.cmd == "list":
        client = YtClient(resolve_cookies_file())
        for tab, kind in TABS:
            entries = client.list_tab(tab)
            print(f"{tab}: {len(entries)}편, 새 편 {merge_listing(rows, entries, kind)}")
        save_index(rows)
        print(f"index: {len(rows)}편")
        return 0
    if a.cmd == "new":
        fresh = [e for e in rss_entries() if e["id"] not in rows]
        for e in fresh:
            merge_listing(rows, [e], e["kind"])
        save_index(rows)
        print(f"새 편 {len(fresh)}:", ", ".join(e["id"] for e in fresh))
        return 0
    store = R2Store.from_env()
    if a.cmd == "pull":
        if store is None:
            print("R2 자격증명 없음", file=sys.stderr)
            return 1
        print(f"캐시로 내려받음 {pull(a.ids, rows, store)}편")
        return 0
    if store is None:
        print("경고: R2 자격증명 없음 — 자막은 로컬 캐시에만 남고 status는 cached가 된다", file=sys.stderr)
    cookie = resolve_cookies_file()
    if not cookie:
        print("경고: 유튜브 쿠키 없음 — 클라우드 IP는 봇 확인에 막힐 수 있다", file=sys.stderr)
    print(f"수집 {fetch_all(rows, YtClient(cookie), store, workers=a.workers, limit=a.limit)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
