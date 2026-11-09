const test = require("node:test");
const assert = require("node:assert");
const { safeUrl, startUrl, visibleStories, splitTop, formatNumber, formatChange, sparkPoints } = require("../site/app.js");

const stories = [
  { rank: 3, topic: "sport" },
  { rank: 1, topic: "klima" },
  { rank: 2, topic: "kultur" },
  { rank: 4, topic: "klima" },
];

test("abgewählte Themen verschwinden und die Rangfolge bleibt", () => {
  const visible = visibleStories(stories, new Set(["kultur"]));
  assert.deepStrictEqual(visible.map((s) => s.rank), [1, 3, 4]);
});

test("nächste Meldungen rücken in die Top-Liste nach", () => {
  const visible = visibleStories(stories, new Set(["klima"]));
  assert.deepStrictEqual(splitTop(visible, 1).top.map((s) => s.rank), [2]);
  assert.deepStrictEqual(splitTop(visible, 1).rest.map((s) => s.rank), [3]);
});

test("alle Themen abgewählt ergibt eine leere Liste", () => {
  assert.strictEqual(visibleStories(stories, new Set(["sport", "klima", "kultur"])).length, 0);
});

test("nur http(s)-Links sind erlaubt", () => {
  assert.strictEqual(safeUrl("javascript:alert(1)"), null);
  assert.strictEqual(safeUrl("data:text/html,x"), null);
  assert.strictEqual(safeUrl("kein link"), null);
  assert.strictEqual(safeUrl("https://example.org/a"), "https://example.org/a");
});

test("der Startlink führt zum Ablauf des eigenen Repositorys", () => {
  assert.strictEqual(startUrl("nuowdnio.github.io", "/morgenbriefing/"), "https://github.com/nuowdnio/morgenbriefing/actions/workflows/briefing.yml");
  assert.strictEqual(startUrl("127.0.0.1", "/"), null);
});

test("Kurse und Veränderungen im deutschen Format", () => {
  assert.strictEqual(formatNumber(24312.4, 0), "24.312");
  assert.strictEqual(formatNumber(1.08234, 4), "1,0823");
  assert.strictEqual(formatChange(1.234, false), "+1,2 %");
  assert.strictEqual(formatChange(-0.05, true), "−0,05 Pp.");
  assert.strictEqual(formatChange(null, false), "–");
});

test("die Kurve füllt die Fläche von unten nach oben", () => {
  assert.strictEqual(sparkPoints([1, 2, 3], 10, 10), "0.0,10.0 5.0,5.0 10.0,0.0");
  assert.strictEqual(sparkPoints([5], 10, 10), "");
});
