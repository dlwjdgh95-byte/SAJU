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
