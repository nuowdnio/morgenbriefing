const test = require("node:test");
const assert = require("node:assert");
const { safeUrl, visibleStories, splitTop } = require("../site/app.js");

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
