// web_parity.test.mjs — 웹 엔진(web/unui-sigantable.html)이 Python 픽스처와 같은 값을 내는지 본다.
//   node --test tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("..", import.meta.url);
const html = readFileSync(new URL("web/unui-sigantable.html", root), "utf8");
// 페이지의 const 선언은 eval로는 밖으로 새지 않는다. new Function으로 감싸 필요한 것만 돌려받는다.
const src = html.slice(html.indexOf("<script>") + 8, html.indexOf("/* ══ 렌더"));
const E = new Function(src + "; return {buildNatal, gyeokCandidates, sinsal12, unseong, gongmang, dayPillar, hourPillar, jieSlot, kmin, currentDaewoonIdx, T};")();
const fx = JSON.parse(readFileSync(new URL("tests/fixtures/natal_cases.json", root), "utf8"));
assert.ok(fx.cases.length >= 38, `픽스처 명조 ${fx.cases.length}개 — 38개 이상이어야 한다 (pytest가 build_fixtures.CASES와 대조)`);

for (const c of fx.cases) {
  test(`${c.date} ${c.time} ${c.gender} — ${c.memo}`, () => {
    const n = E.buildNatal({ date: c.date, time: c.time, timeKnown: true, gender: c.gender });
    const x = c.expect;
    assert.deepEqual(n.pillars, x.pillars, "4기둥");
    assert.equal(n.tz.off, x.offset_min, "UTC 오프셋");
    assert.equal(n.tz.dst, x.dst_min, "서머타임");
    assert.equal(n.tz.corr, x.corr_min, "경도 보정");
    assert.equal(n.dw.forward ? "순행" : "역행", x.daewoon.direction, "대운 방향");
    assert.equal(n.dw.startAge, x.daewoon.start_age, "대운수");
    assert.deepEqual(n.dw.list.map(d => d.gz), x.daewoon.list, "대운 간지");
    assert.deepEqual(n.dw.list.map(d => d.ym), x.daewoon.start, "대운 교체 연월");
    assert.deepEqual(n.pillars.map(p => E.sinsal12(n.yearZhi, p[1])), x.sinsal12_year, "12신살(년지)");
    assert.equal(n.gongmangZhi, x.gongmang, "공망");
    assert.deepEqual(n.pillars.map(p => E.unseong(n.dayGan, p[1])), x.unseong_eum, "십이운성(음포태)");
    assert.deepEqual(n.gyeokList, x.gyeok, "격 후보");
  });
}

test("격 후보 — 24번 원전 명조 전부 Python과 같다 (errata #20)", () => {
  assert.ok(fx.corpus.length >= 86);
  for (const c of fx.corpus) assert.deepEqual(E.gyeokCandidates(c.pillars), c.gyeok, `${c.id} ${c.pillars.join(" ")}`);
});

test("야자시 시주 — 익일 일간으로 시두법 (errata #17)", () => {
  // 2000-01-07 23:50 KST, 보정 없음: 당일 甲子일 → 시주는 익일(乙) 기준 丙子
  const m = E.kmin(new Date(Date.UTC(2000, 0, 7, 23, 50)));
  const today = E.dayPillar(m, false), next = E.dayPillar(m + 1440, false);
  assert.equal(today, "甲子");
  assert.equal(E.hourPillar(today[0], m, next[0]), "丙子");
  assert.equal(E.hourPillar(today[0], m), "甲子", "nextDayGan 없으면 당일 시두법(자시 정설 경로 전용)");
  // 00:00 정각은 야자시 구간의 끝 — 전날 일주·익일 일간 시두법 (saju_calc와 같다, errata #30)
  const mid = E.kmin(new Date(Date.UTC(2000, 0, 8, 0, 0)));
  assert.equal(E.dayPillar(mid, false), "甲子");
  assert.equal(E.hourPillar("甲", mid, "乙"), "丙子");
  assert.equal(E.dayPillar(mid + 1, false), "乙丑");
});

test("현재 대운 — 교체 순간으로 고르고, 10번째가 끝나면 없음", () => {
  const n = E.buildNatal({ date: "1930-05-05", time: "12:00", timeKnown: true, gender: "M" });
  assert.equal(n.dw.list.length, 10);
  const at = s => E.kmin(new Date(Date.parse(s + "T00:00:00Z")));   // KST 눈금
  assert.equal(n.dw.list[E.currentDaewoonIdx(n.dw.list, at("2026-10-22"))].gz, "庚寅");    // 10번째 (2020-09~)
  assert.equal(E.currentDaewoonIdx(n.dw.list, at("2035-01-01")), -1);
  const i = 3, d = n.dw.list[i];
  assert.equal(E.currentDaewoonIdx(n.dw.list, d.startMin - 1), i - 1);
  assert.equal(E.currentDaewoonIdx(n.dw.list, d.startMin), i);
});

test("시각 모름 — 절입일이면 연주·월주 미정 경고", () => {
  const n = E.buildNatal({ date: "2026-02-04", timeKnown: false, gender: "M" });
  assert.ok(n.warn.some(w => w.startsWith("절입일 출생 — 시각을 모르면 연주·월주가")), n.warn.join(" / "));   // 입춘: 연주도 갈린다
  const k = E.buildNatal({ date: "2026-03-05", timeKnown: false, gender: "M" });                       // 경칩: 월주만
  assert.ok(k.warn.some(w => w.startsWith("절입일 출생 — 시각을 모르면 월주가")), k.warn.join(" / "));
  const m = E.buildNatal({ date: "2026-03-15", timeKnown: false, gender: "M" });
  assert.ok(!m.warn.some(w => w.startsWith("절입일 출생")));
  assert.ok(m.warn.some(w => w.includes("23:33 이후 출생이면 일주가 己丑")), m.warn.join(" / "));
  const s = E.buildNatal({ date: "1960-07-01", timeKnown: false, gender: "M" });   // 서머타임: 23:59도 보정 후 당일
  assert.ok(!s.warn.some(w => w.includes("이후 출생이면 일주가")), s.warn.join(" / "));
});

test("시각 보정 경계 — 일주까지 갈리면 둘 다 보여 준다", () => {
  const n = E.buildNatal({ date: "2000-01-07", time: "23:20", timeKnown: true, gender: "M" });
  assert.ok(n.warn.some(w => w.includes("甲子일 乙亥시") && w.includes("乙丑일 丙子시")), n.warn.join(" / "));
});
