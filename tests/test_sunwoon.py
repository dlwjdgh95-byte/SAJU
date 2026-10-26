"""선운의 명리터 수집·카드 검사 — 가짜 클라이언트로 오프라인에서 돈다 (yt-dlp 불필요)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts", "sunwoon"))
import collect as C  # noqa: E402
import cards as K  # noqa: E402


# ── 자막 파서 ──
def test_json3_buckets_by_30s_with_marks():
    ev = [{"tStartMs": 0, "segs": [{"utf8": "가나"}]}, {"tStartMs": 1000, "segs": [{"utf8": "\n"}]},
          {"tStartMs": 12000, "segs": [{"utf8": "다라"}]}, {"tStartMs": 31000, "segs": [{"utf8": "마바"}]},
          {"tStartMs": 3_725_000, "segs": [{"utf8": "사아"}]}]
    assert C.json3_to_timed(json.dumps({"events": ev})).splitlines() == [
        "[0:00] 가나 다라", "[0:31] 마바", "[1:02:05] 사아"]


def test_json3_bad_payload_is_empty():
    assert C.json3_to_timed("not json") == ""


def test_vtt_drops_header_tags_and_rollover_duplicates():
    vtt = ("WEBVTT\nKind: captions\n\n1\n00:00:01.000 --> 00:00:03.000\n<c>갑목은</c>\n\n"
           "00:00:02.000 --> 00:00:04.000\n갑목은\n\n00:00:40.500 --> 00:00:42.000\n을목은\n")
    assert C.vtt_to_timed(vtt).splitlines() == ["[0:01] 갑목은", "[0:40] 을목은"]


# ── 트랙 선택 ──
def _fmts(*exts):
    return [{"ext": e, "url": f"u-{e}"} for e in exts]


def test_manual_beats_auto_and_json3_beats_vtt():
    info = {"subtitles": {"ko-KR": _fmts("vtt", "json3")}, "automatic_captions": {"ko": _fmts("json3")}}
    assert C.pick_track(info) == {"url": "u-json3", "ext": "json3", "lang": "ko-KR", "kind": "manual"}


def test_live_chat_is_not_a_caption_and_auto_ko_is_used():
    info = {"subtitles": {"live_chat": _fmts("json")}, "automatic_captions": {"ko-orig": _fmts("vtt"), "ko": _fmts("json3")}}
    assert C.pick_track(info)["lang"] == "ko"


def test_no_korean_track():
    assert C.pick_track({"automatic_captions": {"en": _fmts("json3")}}) is None


# ── index·수집 ──
def test_merge_listing_keeps_status():
    rows = {"a": {**dict.fromkeys(C.FIELDS, ""), "id": "a", "title": "옛 제목", "status": "fetched"}}
    added = C.merge_listing(rows, [{"id": "a", "title": "새 제목"}, {"id": "b", "title": "b", "duration": 60.0}], "short")
    assert added == 1 and rows["a"]["status"] == "fetched" and rows["a"]["title"] == "새 제목"
    assert rows["b"]["kind"] == "short" and rows["b"]["duration"] == "60" and rows["b"]["status"] == "pending"


class FakeClient:
    def __init__(self, infos, fail=None):
        self.infos, self.fail, self.calls = infos, dict(fail or {}), []

    def video_info(self, vid):
        self.calls.append(vid)
        if self.fail.get(vid):
            self.fail[vid] -= 1
            raise RuntimeError("Sign in to confirm you're not a bot")
        return self.infos[vid]

    def fetch(self, url):
        return json.dumps({"events": [{"tStartMs": 0, "segs": [{"utf8": url}]}]}).encode()


class FakeStore:
    def __init__(self):
        self.objs = {}

    def put(self, key, data):
        self.objs[key] = data

    def get(self, key):
        return self.objs[key]


def _rows(*ids, status="pending"):
    return {i: {**dict.fromkeys(C.FIELDS, ""), "id": i, "status": status} for i in ids}


def _info(vid, auto=True):
    return {"id": vid, "timestamp": 1_700_000_000, "duration": 100,
            "automatic_captions": {"ko": _fmts("json3")} if auto else {}}


def test_fetch_all_writes_cache_and_r2_and_skips_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE", tmp_path)
    rows = _rows("a", "b", "c")
    rows["c"]["status"] = "fetched"
    store = FakeStore()
    client = FakeClient({"a": _info("a"), "b": _info("b", auto=False)})
    counts = C.fetch_all(rows, client, store, workers=2, save=lambda r: None, log=lambda *a: None)
    assert counts == {"fetched": 1, "no_caption": 1}
    assert sorted(client.calls) == ["a", "b"]
    assert rows["a"]["published"] == "2023-11-15" and rows["a"]["caption"] == "auto"
    assert store.objs[C.transcript_key("a")] == (tmp_path / "a.txt").read_bytes()
    assert rows["b"]["status"] == "no_caption"


def test_block_signal_backs_off_then_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE", tmp_path)
    slept = []
    rows = _rows("a")
    client = FakeClient({"a": _info("a")}, fail={"a": 2})
    C.fetch_all(rows, client, FakeStore(), workers=1, backoff=1, save=lambda r: None,
                sleep=slept.append, log=lambda *a: None)
    assert rows["a"]["status"] == "fetched" and slept == [1, 3]


def test_non_block_error_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE", tmp_path)
    rows = _rows("a")
    C.fetch_all(rows, FakeClient({}), FakeStore(), workers=1, save=lambda r: None, log=lambda *a: None)
    assert rows["a"]["status"].startswith("error:")


def test_index_roundtrip(tmp_path):
    rows = _rows("b", "a")
    rows["a"]["published"] = "2020-01-01"
    p = tmp_path / "i.csv"
    C.save_index(rows, p)
    assert list(C.load_index(p)) == ["a", "b"]


def test_pull_skips_matching_cache(tmp_path):
    store = FakeStore()
    store.put(C.transcript_key("a"), b"x")
    rows = _rows("a", status="fetched")
    assert C.pull([], rows, store, cache=tmp_path) == 1
    assert C.pull([], rows, store, cache=tmp_path) == 0


# ── 카드 검사 ──
GOOD = """---
id: v1
title: 술토 이야기
date: 2026-10-25
kind: video
tags: [지장간, 십성]
quality: good
---
## 요지
- 술토 속 무토는 밖으로 드러나는 승부의 힘으로 본다
- 기토는 조심스럽게 살피는 쪽의 작용으로 본다
- 두 토의 쓰임을 구분해야 월지 술토를 제대로 읽는다

## 주장
1. 술월생은 무토가 드러나면 경쟁에 강하다 @1:05
2. 기토는 「간을 본다」는 탐색의 작용 @12:30

## 사례
- 없음

## 저장소 대조
- 35 잡기: 보강 — 사고지 토의 이중 작용 서술 추가 후보
"""


def _lint(tmp_path, text, transcript=None, duration="900"):
    card = tmp_path / "cards" / "v1.md"
    card.parent.mkdir()
    card.write_text(text, encoding="utf-8")
    if transcript is not None:
        (tmp_path / "v1.txt").write_text(transcript, encoding="utf-8")
    index = {"v1": {**dict.fromkeys(C.FIELDS, ""), "id": "v1", "published": "2026-10-25",
                    "duration": duration, "status": "fetched"}}
    return K.lint_card(card, index, {"지장간", "십성", "천간"}, cache=tmp_path)


def test_good_card_passes(tmp_path):
    assert _lint(tmp_path, GOOD, transcript="[0:00] 전혀 다른 말들이 이어진다") == []


def test_taxonomy_file_tags_are_parsed():
    tags = K.load_tags()
    assert {"천간", "지장간", "십성", "기타"} <= tags


def test_bad_tag_and_missing_timestamp(tmp_path):
    bad = GOOD.replace("[지장간, 십성]", "[지장간, 오행론]").replace(" @1:05", "")
    errs = _lint(tmp_path, bad)
    assert any("taxonomy 밖" in e for e in errs) and any("출처 시각" in e for e in errs)


def test_timestamp_past_duration(tmp_path):
    assert any("영상 길이" in e for e in _lint(tmp_path, GOOD, duration="60"))


def test_long_quote_fails(tmp_path):
    bad = GOOD.replace("「간을 본다」", "「" + "가" * 21 + "」")
    assert any("인용" in e for e in _lint(tmp_path, bad))


def test_verbatim_copy_from_transcript_fails(tmp_path):
    spoken = "술토 속 무토는 밖으로 드러나는 승부의 힘으로 본다"
    errs = _lint(tmp_path, GOOD, transcript=f"[1:00] 음 {spoken} 그렇죠")
    assert any("그대로 옮겼다" in e for e in errs)


def test_section_order_and_gist_count(tmp_path):
    bad = GOOD.replace("## 사례\n- 없음\n\n", "")
    assert any("절 순서" in e for e in _lint(tmp_path, bad))


def test_todo_batches_oldest_first(tmp_path):
    idx = {i: {**dict.fromkeys(C.FIELDS, ""), "id": i, "published": d, "status": s}
           for i, d, s in [("x", "2020-01-02", "fetched"), ("y", "2019-05-05", "fetched"),
                           ("z", "2021-01-01", "pending"), ("w", "2018-01-01", "fetched")]}
    (tmp_path / "w.md").write_text("done")
    assert K.todo(idx, cards=tmp_path, batch=1) == [["y"], ["x"]]


def test_quality_required(tmp_path):
    assert any("quality" in e for e in _lint(tmp_path, GOOD.replace("quality: good\n", "")))
