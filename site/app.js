/* Zeigt das Briefing an. Feed-Texte werden nur per textContent eingefügt und so sicher escaped. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else api.start(root);
})(typeof window !== "undefined" ? window : globalThis, function () {
  const STORAGE_KEY = "briefing.topics.off";
  const THEME_KEY = "briefing.theme";
  const MARKETS_ID = "maerkte";
  const SVG_NS = "http://www.w3.org/2000/svg";

  function safeUrl(value) {
    try {
      const url = new URL(String(value));
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
    } catch (error) {
      return null;
    }
  }

  function startUrl(hostname, pathname) {
    const owner = /^([a-z0-9-]+)\.github\.io$/i.exec(hostname || "");
    const repo = /^\/([A-Za-z0-9._-]+)/.exec(pathname || "");
    if (!owner || !repo) return null;
    return "https://github.com/" + owner[1] + "/" + repo[1] + "/actions/workflows/briefing.yml";
  }

  function visibleStories(stories, offTopics) {
    return stories
      .filter(function (story) { return !offTopics.has(story.topic); })
      .sort(function (a, b) { return a.rank - b.rank; });
  }

  function splitTop(stories, topCount) {
    return { top: stories.slice(0, topCount), rest: stories.slice(topCount) };
  }


  function formatNumber(value, decimals) {
    return Number(value).toLocaleString("de-DE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }

  function formatChange(value, absolute) {
    if (value === null || value === undefined) return "–";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
    return sign + formatNumber(Math.abs(value), absolute ? 2 : 1) + (absolute ? " Pp." : " %");
  }

  function sparkPoints(values, width, height) {
    if (!values || values.length < 2) return "";
    const min = Math.min.apply(null, values);
    const max = Math.max.apply(null, values);
    const span = max - min || 1;
    return values.map(function (value, index) {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
  }

  function direction(value) {
    return value > 0 ? "up" : value < 0 ? "down" : "flat";
  }

  function read(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }

  function write(key, value) {
    try { window.localStorage.setItem(key, value); } catch (error) { /* Speichern nicht möglich */ }
  }

  function loadOffTopics() {
    try {
      const stored = JSON.parse(read(STORAGE_KEY) || "[]");
      return new Set(Array.isArray(stored) ? stored : []);
    } catch (error) {
      return new Set();
    }
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function sourceLabel(count) {
    return count === 1 ? "1 Quelle" : count + " Quellen";
  }

  function renderStory(story, topicLabels, showTopic) {
    const article = element("article", "story");
    article.append(element("h3", "", story.title));
    if (story.summary && story.summary.length) {
      article.append(element("p", "summary", story.summary.join(" ")));
    }
    const badges = element("p", "badges");
    if (showTopic) badges.append(element("span", "", topicLabels[story.topic] || ""));
    if (story.single_source) badges.append(element("span", "badge-single", "Nur eine Quelle"));
    else badges.append(element("span", "", sourceLabel(story.source_count)));
    if (story.machine_translated) badges.append(element("span", "", "Maschinell übersetzt"));
    article.append(badges);
    if (story.details && story.details.length) {
      const more = element("details", "more");
      more.append(element("summary", "", "Mehr dazu"));
      story.details.forEach(function (detail) {
        const block = element("div", "more-item");
        block.append(element("p", "more-source", detail.source + " · " + detail.country));
        if (detail.title) block.append(element("p", "more-title", detail.title));
        if (detail.text && detail.text.length) block.append(element("p", "more-text", detail.text.join(" ")));
        const detailHref = safeUrl(detail.url);
        if (detailHref) {
          const full = element("a", "more-link", "Ganzen Artikel bei " + detail.source + " lesen");
          full.href = detailHref;
          full.rel = "noopener noreferrer nofollow";
          block.append(full);
        }
        more.append(block);
      });
      article.append(more);
    }
    const links = element("p", "links");
    links.append(element("span", "links-label", "Ganzer Artikel: "));
    (story.links || []).forEach(function (link) {
      const href = safeUrl(link.url);
      if (!href) return;
      const anchor = element("a", "", link.source);
      anchor.href = href;
      anchor.rel = "noopener noreferrer nofollow";
      anchor.title = link.country + ", " + link.ownership;
      links.append(anchor);
    });
    article.append(links);
    return article;
  }

  function sparkline(values) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 80 24");
    svg.setAttribute("class", "spark spark-" + direction(values[values.length - 1] - values[0]));
    svg.setAttribute("aria-hidden", "true");
    const line = document.createElementNS(SVG_NS, "polyline");
    line.setAttribute("points", sparkPoints(values, 80, 22));
    line.setAttribute("transform", "translate(0 1)");
    svg.append(line);
    return svg;
  }

  function changeCell(tag, value, absolute) {
    const parts = tag.split(" ");
    return element(parts[0], ["num change change-" + direction(value || 0)].concat(parts.slice(1)).join(" "), formatChange(value, absolute));
  }

  function priceText(item) {
    return (formatNumber(item.price, item.decimals) + " " + (item.unit || "")).trim();
  }

  function quoteTable(items, withSpark) {
    const table = element("table", "quotes");
    const head = element("tr");
    ["Wert", "Stand", "Tag", "1 Monat", "lfd. Jahr"].forEach(function (label, index) {
      const cell = element("th", (index ? "num" : "") + (index === 3 ? " col-1m" : ""), label);
      cell.scope = "col";
      head.append(cell);
    });
    if (withSpark) head.append(element("th", "spark-col", "3 Monate"));
    const thead = element("thead");
    thead.append(head);
    table.append(thead);
    const body = element("tbody");
    items.forEach(function (item) {
      const absolute = item.kind === "yield";
      const row = element("tr");
      const name = element("th", "");
      name.scope = "row";
      name.append(element("span", "quote-name", item.name));
      if (item.trend || item.sector) name.append(element("span", "quote-sub", item.sector || item.trend));
      row.append(name, element("td", "num", priceText(item)),
        changeCell("td", item.change_1d, absolute), changeCell("td col-1m", item.change_1m, absolute),
        changeCell("td", item.change_ytd, absolute));
      if (withSpark) {
        const cell = element("td", "spark-col");
        if (item.spark && item.spark.length > 1) cell.append(sparkline(item.spark));
        row.append(cell);
      }
      body.append(row);
    });
    table.append(body);
    return table;
  }

  function storyLinks(stories) {
    const list = element("ul", "related");
    (stories || []).forEach(function (story) {
      const href = safeUrl(story.url);
      if (!href) return;
      const item = element("li");
      const anchor = element("a", "", story.title);
      anchor.href = href;
      anchor.rel = "noopener noreferrer nofollow";
      item.append(anchor);
      list.append(item);
    });
    return list;
  }

  function renderMarkets(markets) {
    const section = element("section", "section markets");
    section.id = "maerkte";
    section.append(element("h2", "", "Börse & Märkte"));
    if (!markets.available) {
      section.append(element("p", "empty", "Kursdaten waren heute nicht abrufbar. Die Nachrichten oben sind vollständig."));
      return section;
    }
    if (markets.summary) section.append(element("p", "market-summary", markets.summary));
    if (markets.as_of) {
      section.append(element("p", "meta", "Letzte Kurse vom " + new Date(markets.as_of + "T12:00:00Z").toLocaleDateString("de-DE",
        { timeZone: "Europe/Berlin", weekday: "long", day: "numeric", month: "long" }) +
        ". „Tag“ = Veränderung zur vorherigen Sitzung."));
    }
    (markets.groups || []).forEach(function (group) {
      section.append(element("h3", "market-head", group.label));
      const wrap = element("div", "table-wrap");
      wrap.append(quoteTable(group.items, true));
      section.append(wrap);
    });

    if (markets.watch && markets.watch.length) {
      section.append(element("h3", "market-head", "Unternehmen im Blick"));
      section.append(element("p", "meta", "Ausgewählt nach ungewöhnlichen Kursbewegungen, Jahreshochs und -tiefs und Erwähnungen in den heutigen Nachrichten."));
      const list = element("ul", "watch");
      markets.watch.forEach(function (item) {
        const card = element("li", "watch-item");
        const head = element("p", "watch-head");
        head.append(element("strong", "", item.name), element("span", "quote-sub", item.sector));
        card.append(head);
        const figures = element("p", "watch-figures");
        figures.append(element("span", "num", priceText(item)), element("span", "", "Tag "),
          changeCell("span", item.change_1d, false), element("span", "", " · Monat "),
          changeCell("span", item.change_1m, false));
        card.append(figures);
        const reasons = element("ul", "reasons");
        (item.reasons || []).forEach(function (reason) { reasons.append(element("li", "", reason)); });
        card.append(reasons);
        if (item.stories && item.stories.length) card.append(storyLinks(item.stories));
        list.append(card);
      });
      section.append(list);
    }

    if (markets.trends && markets.trends.length) {
      section.append(element("h3", "market-head", "Trends"));
      section.append(element("p", "meta", "Wie oft ein Thema heute in den Nachrichten vorkommt (verglichen mit den letzten 7 Tagen) und wie sich passende Aktien im letzten Monat entwickelt haben."));
      const list = element("ul", "trends");
      markets.trends.forEach(function (trend) {
        const item = element("li", "trend-item");
        item.append(element("strong", "", trend.label));
        let news = trend.mentions === 0 ? "Heute keine Artikel" : trend.mentions === 1 ? "1 Artikel heute" : trend.mentions + " Artikel heute";
        if (trend.direction) news += " – " + trend.direction + " (Ø " + formatNumber(trend.average, 1) + ")";
        item.append(element("p", "trend-line trend-" + (trend.direction === "mehr als üblich" ? "hot" : "normal"), news));
        if (trend.basket_1m !== null && trend.basket_1m !== undefined) {
          const market = element("p", "trend-line");
          market.append(element("span", "", "Passende Werte im Monat: "), changeCell("span", trend.basket_1m, false));
          const members = (trend.members || []).map(function (m) { return m.name + " " + formatChange(m.change_1m, false); });
          if (members.length) market.append(element("span", "quote-sub block", members.join(" · ")));
          item.append(market);
        }
        if (trend.stories && trend.stories.length) item.append(storyLinks(trend.stories));
        list.append(item);
      });
      section.append(list);
    }

    if (markets.companies && markets.companies.length) {
      const all = element("details", "more");
      all.append(element("summary", "", "Alle beobachteten Unternehmen (" + markets.companies.length + ")"));
      const wrap = element("div", "table-wrap");
      wrap.append(quoteTable(markets.companies, false));
      all.append(wrap);
      section.append(all);
    }
    const failed = markets.failed && markets.failed.length ? " Heute ohne Kurs: " + markets.failed.join(", ") + "." : "";
    section.append(element("p", "note", "Quelle: " + markets.source + ". Keine Anlageberatung." + failed));
    return section;
  }

  function start() {
    const state = { off: loadOffTopics(), data: null };
    const content = document.getElementById("content");

    function persist() {
      write(STORAGE_KEY, JSON.stringify(Array.from(state.off)));
    }

    function renderChips() {
      const holder = document.getElementById("topics");
      holder.replaceChildren();
      state.data.topics.forEach(function (topic) {
        const chip = element("button", "chip", topic.label);
        chip.type = "button";
        chip.id = "topic-" + topic.id;
        chip.setAttribute("aria-pressed", String(!state.off.has(topic.id)));
        chip.addEventListener("click", function () {
          if (state.off.has(topic.id)) state.off.delete(topic.id);
          else state.off.add(topic.id);
          persist();
          renderChips();
          renderStories();
        });
        holder.append(chip);
      });
      if (state.data.markets) {
        const chip = element("button", "chip", "Börse & Märkte");
        chip.type = "button";
        chip.id = "topic-" + MARKETS_ID;
        chip.setAttribute("aria-pressed", String(!state.off.has(MARKETS_ID)));
        chip.addEventListener("click", function () {
          if (state.off.has(MARKETS_ID)) state.off.delete(MARKETS_ID);
          else state.off.add(MARKETS_ID);
          persist();
          renderChips();
          renderStories();
        });
        holder.append(chip);
      }
    }

    function renderStories() {
      const data = state.data;
      const labels = Object.fromEntries(data.topics.map(function (t) { return [t.id, t.label]; }));
      const visible = visibleStories(data.stories, state.off);
      content.replaceChildren();
      const showMarkets = data.markets && !state.off.has(MARKETS_ID);
      if (!visible.length) {
        content.append(element("p", "empty", "Keine Meldungen. Wähle oben mindestens ein Thema aus."));
        if (showMarkets) content.append(renderMarkets(data.markets));
        return;
      }
      const parts = splitTop(visible, data.top_count);
      const topSection = element("section", "section");
      topSection.append(element("h2", "", "Das Wichtigste"));
      const list = element("ol", "top-list");
      parts.top.forEach(function (story) {
        const item = element("li");
        item.append(renderStory(story, labels, true));
        list.append(item);
      });
      topSection.append(list);
      content.append(topSection);
      data.topics.forEach(function (topic) {
        const stories = parts.rest.filter(function (story) { return story.topic === topic.id; });
        if (!stories.length) return;
        const section = element("section", "section");
        section.append(element("h2", "", topic.label));
        const items = element("ul", "stories");
        stories.forEach(function (story) {
          const item = element("li");
          item.append(renderStory(story, labels, false));
          items.append(item);
        });
        section.append(items);
        content.append(section);
      });
      if (showMarkets) content.append(renderMarkets(data.markets));
    }

    function renderMeta() {
      const data = state.data;
      const created = new Date(data.generated_at);
      const berlin = { timeZone: "Europe/Berlin" };
      document.getElementById("date").textContent = new Date(data.date + "T12:00:00Z").toLocaleDateString("de-DE",
        Object.assign({ weekday: "long", day: "numeric", month: "long", year: "numeric" }, berlin));
      document.getElementById("stand").textContent = "Stand " + created.toLocaleTimeString("de-DE",
        Object.assign({ hour: "2-digit", minute: "2-digit" }, berlin)) + " Uhr · Meldungen der letzten " +
        data.window_hours + " Stunden · " + data.stories.length + " Meldungen";
      const ok = data.sources.filter(function (s) { return s.ok; });
      const failed = data.sources.filter(function (s) { return !s.ok; });
      const problems = failed.map(function (s) { return s.name; }).join(", ");
      const warnings = (data.warnings || []).join(" ");
      document.getElementById("source-problems").textContent =
        (failed.length ? "Heute nicht verfügbar: " + problems + ". " : "") + warnings;
      document.getElementById("source-summary").textContent =
        "Quellen: " + ok.length + " von " + data.sources.length + " verfügbar";
      const list = document.getElementById("source-list");
      list.replaceChildren();
      data.sources.forEach(function (source) {
        const state_text = source.ok ? "" : " – nicht verfügbar: " + source.reason;
        list.append(element("li", "", source.name + " (" + source.country + ", " + source.ownership + ")" + state_text));
      });
    }

    function fetchJson(path) {
      return fetch(path, { cache: "no-cache" }).then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      });
    }

    function showDay(day) {
      return fetchJson("data/" + day + ".json").then(function (data) {
        state.data = data;
        renderMeta();
        renderChips();
        renderStories();
      });
    }

    function showError() {
      document.getElementById("date").textContent = "Noch kein Briefing";
      content.replaceChildren(element("p", "empty",
        "Das Briefing konnte nicht geladen werden. Beim ersten Einrichten erscheint es nach dem ersten erfolgreichen Lauf."));
    }

    function setTheme(theme) {
      if (theme) document.documentElement.dataset.theme = theme;
      const dark = document.documentElement.dataset.theme === "dark" ||
        (!document.documentElement.dataset.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.getElementById("theme").textContent = dark ? "Hell" : "Dunkel";
    }

    const restart = startUrl(window.location.hostname, window.location.pathname);
    if (restart) {
      document.getElementById("restart-link").href = restart;
      document.getElementById("restart").hidden = false;
    }

    setTheme(read(THEME_KEY));
    document.getElementById("theme").addEventListener("click", function () {
      const next = document.getElementById("theme").textContent === "Dunkel" ? "dark" : "light";
      write(THEME_KEY, next);
      setTheme(next);
    });
    document.getElementById("all").addEventListener("click", function () {
      state.off.clear();
      persist();
      renderChips();
      renderStories();
    });
    document.getElementById("none").addEventListener("click", function () {
      state.data.topics.forEach(function (topic) { state.off.add(topic.id); });
      state.off.add(MARKETS_ID);
      persist();
      renderChips();
      renderStories();
    });

    fetchJson("data/index.json").then(function (index) {
      const select = document.getElementById("archive");
      index.dates.forEach(function (day) {
        const option = element("option", "", new Date(day + "T12:00:00Z").toLocaleDateString("de-DE", { timeZone: "Europe/Berlin", weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" }));
        option.value = day;
        select.append(option);
      });
      select.addEventListener("change", function () { showDay(select.value).catch(showError); });
      return showDay(index.dates[0]);
    }).catch(showError);
  }

  return {
    safeUrl: safeUrl, startUrl: startUrl, visibleStories: visibleStories, splitTop: splitTop,
    formatNumber: formatNumber, formatChange: formatChange, sparkPoints: sparkPoints, start: start,
  };
});
