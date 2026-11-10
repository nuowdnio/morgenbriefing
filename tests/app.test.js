const test = require("node:test");
const assert = require("node:assert");
const { safeUrl, startUrl, repoFromLocation, validToken, findRun, runStatusText, visibleStories, splitTop, formatNumber, formatChange, sparkPoints } = require("../site/app.js");

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

test("Repository wird aus der Adresse der Seite erkannt", () => {
  assert.deepStrictEqual(repoFromLocation("nuowdnio.github.io", "/morgenbriefing/"), { owner: "nuowdnio", repo: "morgenbriefing" });
  assert.strictEqual(repoFromLocation("example.org", "/x/"), null);
});

test("nur echte GitHub-Tokens werden gespeichert", () => {
  assert.ok(validToken("github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz"));
  assert.ok(!validToken("mein passwort"));
  assert.ok(!validToken("github_pat_<script>"));
});

test("der eigene Lauf wird gefunden, ältere nicht", () => {
  const since = Date.parse("2026-11-10T08:00:00Z");
  const runs = [
    { event: "workflow_dispatch", created_at: "2026-11-10T07:30:00Z", status: "completed" },
    { event: "schedule", created_at: "2026-11-10T08:00:10Z", status: "queued" },
    { event: "workflow_dispatch", created_at: "2026-11-10T08:00:05Z", status: "in_progress", id: 7 },
  ];
  assert.strictEqual(findRun(runs, since).id, 7);
  assert.strictEqual(findRun(runs.slice(0, 2), since), null);
});

test("Statusmeldungen während des Laufs", () => {
  const since = 0;
  assert.match(runStatusText(null, 1000, since), /Wartet auf GitHub/);
  assert.match(runStatusText({ status: "in_progress" }, 3 * 60000, since), /seit 3 Min/);
  assert.match(runStatusText({ status: "completed", conclusion: "success" }, 1, since), /Fertig/);
  assert.match(runStatusText({ status: "completed", conclusion: "failure" }, 1, since), /fehlgeschlagen/);
});
