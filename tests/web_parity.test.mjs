// web_parity.test.mjs — 웹 엔진(web/unui-sigantable.html)이 Python 픽스처와 같은 값을 내는지 본다.
//   node --test tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("..", import.meta.url);
const html = readFileSync(new URL("web/unui-sigantable.html", root), "utf8");
// 페이지의 const 선언은 eval로는 밖으로 새지 않는다. new Function으로 감싸 필요한 것만 돌려받는다.
const src = html.slice(html.indexOf("<script>") + 8, html.indexOf("/* ══ 렌더"));
const E = new Function(src + "; return {buildNatal, gyeokCandidates, sinsal12, unseong, gongmang, dayPillar, hourPillar, jieSlot, kmin, T};")();
const fx = JSON.parse(readFileSync(new URL("tests/fixtures/natal_cases.json", root), "utf8"));

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
});
