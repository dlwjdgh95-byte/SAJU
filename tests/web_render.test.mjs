// web_render.test.mjs — 페이지 전체 스크립트(렌더 포함)를 최소 DOM 대역으로 돌려 본다. 렌더 코드의 오타·예외를 CI에서 잡는다.
//   node --test tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../web/unui-sigantable.html", import.meta.url), "utf8");
const src = html.slice(html.indexOf("<script>") + 8, html.lastIndexOf("</script>"));

function mkEl(id) {
  return { id, innerHTML: "", textContent: "", style: {}, dataset: {}, children: [], hidden: false, open: false, value: "",
    className: "", append(...c) { this.children.push(...c); }, setAttribute() {}, addEventListener() {},
    querySelector() { return mkEl("q"); } };
}
const els = {};
const form = mkEl("birthForm");
for (const k of ["bname", "bdate", "btime", "bunknown", "bgender"]) form[k] = { value: "" };
els.birthForm = form;
const document = { getElementById: id => (els[id] ||= mkEl(id)), createElement: t => mkEl(t) };
const store = {};
const localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } };
const { boot } = new Function("document", "window", "localStorage", src + "; return { boot };")(document, { scrollTo() {} }, localStorage);

const profiles = [
  { date: "1995-10-29", time: "06:30", timeKnown: true, gender: "M" },
  { date: "2026-02-04", timeKnown: false, gender: "F" },          // 시각 모름 + 절입일
  { date: "1900-02-05", time: "00:00", timeKnown: true, gender: "F" },
  { date: "2045-12-31", time: "23:59", timeKnown: true, gender: "M" },
  { date: "2000-01-07", time: "23:20", timeKnown: true, gender: "M" },  // 보정 경계
  { date: "1930-05-05", time: "12:00", timeKnown: true, gender: "M" },  // 10번째 대운까지
];
for (const p of profiles) {
  test(`렌더 — ${p.date} ${p.time ?? "시각 모름"}`, () => {
    for (const k of ["todayGz", "daewoonKv", "structKv"]) els[k].innerHTML = "";   // 앞 명조의 렌더가 남아 통과하지 않게
    boot({ name: "", ...p });
    assert.ok(els.todayGz.innerHTML.length > 0, "오늘 일진");
    assert.ok(els.daewoonKv.innerHTML.length > 0, "대운");
    assert.ok(els.structKv.innerHTML.length > 0, "원국 구조");
  });
}

test("렌더 — 경고 목록은 '확인' 칸에 나온다", () => {
  boot({ name: "", date: "2026-02-04", timeKnown: false, gender: "F" });
  assert.ok(els.structKv.innerHTML.includes("<dt>확인</dt>") && els.structKv.innerHTML.includes("절입일 출생"));
});

test("렌더 — 일간 뿌리가 없으면 4기둥은 무근, 3기둥은 '연·월·일지에 뿌리 없음'", () => {
  boot({ name: "", date: "1990-01-09", time: "12:00", timeKnown: true, gender: "M" });     // 己巳 丁丑 甲戌 庚午
  assert.ok(els.structKv.innerHTML.includes("<b>무근(無根)</b>"), els.structKv.innerHTML);
  boot({ name: "", date: "1990-01-09", timeKnown: false, gender: "M" });
  assert.ok(els.structKv.innerHTML.includes("<b>연·월·일지에 뿌리 없음</b> (시지 미상)"), els.structKv.innerHTML);
});

test("주운 — 월요일에 시작한다", () => {
  const t0 = Date.parse("2026-10-22T03:00:00Z");                    // 목요일 KST 정오
  class FixedDate extends Date { constructor(...a) { super(...(a.length ? a : [t0])); } static now() { return t0; } }
  const { computePeriods, buildNatal } = new Function("document", "window", "localStorage", "Date",
    src + "; return { computePeriods, buildNatal };")(document, { scrollTo() {} }, localStorage, FixedDate);
  const p = computePeriods(buildNatal({ date: "1995-10-29", time: "06:30", timeKnown: true, gender: "M" }));
  assert.equal(p.week0.note, "10/19 월요일 → 10/25 일요일");
  assert.equal(p.week1.note, "10/26 월요일 → 11/01 일요일");
  assert.equal(p.week0.days.findIndex(d => d.isToday), 3);
});

test("아침 글 — 같은 날짜·시각이어도 시각을 모름으로 바꾸면 기본 명식 글을 붙이지 않는다", () => {
  const block = src.slice(src.indexOf("const DAILY"));
  const day = block.match(/for: "(\d{4}-\d{2}-\d{2})"/)[1], title = block.match(/title: "([^"]+)"/)[1];
  const [date, time, gender] = block.match(/profile: "([^"]+)"/)[1].split("|");
  const t0 = Date.parse(`${day}T03:00:00Z`);                         // 그날 KST 정오
  class FixedDate extends Date { constructor(...a) { super(...(a.length ? a : [t0])); } static now() { return t0; } }
  const { boot: b } = new Function("document", "window", "localStorage", "Date", src + "; return { boot };")(document, { scrollTo() {} }, localStorage, FixedDate);
  b({ name: "", date, time, timeKnown: true, gender });
  assert.ok(els.daily.innerHTML.includes(title), "기본 명식이면 아침 글");
  b({ name: "", date, time, timeKnown: false, gender });
  assert.ok(!els.daily.innerHTML.includes(title), "시각 모름이면 계산값");
});

test("십성 인종 — 세력 점수가 아니라 32번 규범(슬롯·원국 교차·사고지 개폐)으로 쓴다", () => {
  const t0 = Date.parse("2026-10-23T03:00:00Z");                    // 戊戌월
  class FixedDate extends Date { constructor(...a) { super(...(a.length ? a : [t0])); } static now() { return t0; } }
  const { boot: b } = new Function("document", "window", "localStorage", "Date", src + "; return { boot };")(document, { scrollTo() {} }, localStorage, FixedDate);
  b({ name: "", date: "1990-05-15", time: "09:30", timeKnown: true, gender: "M" });   // 庚午 辛巳 庚辰 庚辰
  const pr = els.prose.innerHTML;
  assert.ok(!pr.includes("쓸 수 있는 카드") && !pr.includes("기대를 낮출 영역"), pr);
  assert.ok(pr.includes("<b>창고</b>") && pr.includes("충으로 창고 문이 열립니다"), "辰戌충 — 충개고 (Python --injong 戊戌과 같다)");
  assert.ok(pr.includes("이중 입묘는 편인"), "戌 지장간 戊 = 편인이 墓");
  assert.ok(pr.includes("식신") && pr.includes("허상"), "원국에 없는 壬(식신)이 관대 — 허상");
  assert.ok(els.ledger.children.some(c => c.innerHTML.includes("사고지 개폐: <b>충개고</b>")), "원장 줄");
});
