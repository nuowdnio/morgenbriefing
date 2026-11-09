/* Zeigt das Briefing an. Feed-Texte werden nur per textContent eingefügt und so sicher escaped. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else api.start(root);
})(typeof window !== "undefined" ? window : globalThis, function () {
  const STORAGE_KEY = "briefing.topics.off";
  const THEME_KEY = "briefing.theme";

  function safeUrl(value) {
    try {
      const url = new URL(String(value));
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
    } catch (error) {
      return null;
    }
  }

  function visibleStories(stories, offTopics) {
    return stories
      .filter(function (story) { return !offTopics.has(story.topic); })
      .sort(function (a, b) { return a.rank - b.rank; });
  }

  function splitTop(stories, topCount) {
    return { top: stories.slice(0, topCount), rest: stories.slice(topCount) };
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
    }

    function renderStories() {
      const data = state.data;
      const labels = Object.fromEntries(data.topics.map(function (t) { return [t.id, t.label]; }));
      const visible = visibleStories(data.stories, state.off);
      content.replaceChildren();
      if (!visible.length) {
        content.append(element("p", "empty", "Keine Meldungen. Wähle oben mindestens ein Thema aus."));
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

  return { safeUrl: safeUrl, visibleStories: visibleStories, splitTop: splitTop, start: start };
});
