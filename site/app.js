import { compact, decimal, technicalOption, technicalRows } from "./charts.js";

const $ = (id) => document.getElementById(id);
let manifest,
  selected,
  dataset,
  chart,
  observer,
  pending,
  generation = 0;
let range = "6";
const money = (value, currency = "") =>
  value == null ? "—" : `${decimal(value)}${currency ? " " + currency : ""}`;
const conditionClass = (value) => value.toLowerCase();

function disposeChart() {
  observer?.disconnect();
  observer = undefined;
  chart?.dispose();
  chart = undefined;
  $("chart").replaceChildren();
}

function visibleSecurities() {
  const search = $("search").value.trim().toLowerCase();
  const rows = manifest.securities.filter(
    (item) =>
      (!search ||
        `${item.ticker} ${item.symbol} ${item.name}`
          .toLowerCase()
          .includes(search)) &&
      (!$("condition").value || item.condition === $("condition").value) &&
      (!$("universe").value || item.universe === $("universe").value),
  );
  return rows.sort((a, b) => {
    const sort = $("sort").value;
    if (sort !== "ticker") {
      if (a.rsi == null && b.rsi != null) return 1;
      if (b.rsi == null && a.rsi != null) return -1;
      if (a.rsi !== b.rsi)
        return (sort === "rsi-asc" ? 1 : -1) * (a.rsi - b.rsi);
    }
    return a.ticker.localeCompare(b.ticker);
  });
}

function renderList() {
  const rows = visibleSecurities();
  $("count").textContent = `${rows.length} / ${manifest.securities.length}`;
  $("list-empty").hidden = Boolean(rows.length);
  $("list").replaceChildren(
    ...rows.map((item) => {
      const button = document.createElement("button");
      button.className = "security-row";
      button.dataset.symbol = item.symbol;
      button.setAttribute(
        "aria-current",
        String(item.symbol === selected?.symbol),
      );
      button.setAttribute(
        "aria-label",
        `${item.ticker}, ${item.name}, ${item.condition}${item.stale ? ", stale data" : ""}`,
      );
      // Static structure only; every registry field is assigned through textContent.
      button.innerHTML =
        '<div class="row-top"><strong></strong><span class="quote"></span></div><div class="row-name"></div><div class="row-bottom"><span class="condition"></span><span class="row-rsi"></span></div><div class="row-meta"></div>';
      button.querySelector("strong").textContent = item.ticker;
      button.querySelector(".quote").textContent = money(
        item.close,
        item.currency,
      );
      button.querySelector(".row-name").textContent = item.name;
      const condition = button.querySelector(".condition");
      condition.textContent = item.condition;
      condition.classList.add(conditionClass(item.condition));
      button.querySelector(".row-rsi").textContent =
        `RSI ${item.rsi == null ? "—" : item.rsi.toFixed(1)}`;
      button.querySelector(".row-meta").textContent =
        `${item.market} · ${item.universe.replaceAll("_", " ")} · ${item.last_date ?? "No prices"}${item.stale ? " · Stale" : ""}`;
      button.addEventListener("click", () => select(item.symbol));
      return button;
    }),
  );
}

function startIndex() {
  if (range === "all") return 0;
  const rows = dataset.rows;
  const start = new Date(rows.at(-1)[0] + "T00:00:00Z");
  start.setUTCMonth(start.getUTCMonth() - Number(range));
  const day = start.toISOString().slice(0, 10);
  return Math.max(
    0,
    rows.findIndex((row) => row[0] >= day),
  );
}

function draw() {
  if (!dataset || !chart) return;
  const currentZoom = chart.getOption()?.dataZoom?.[0];
  const option = technicalOption(
    dataset,
    selected.currency,
    manifest.thresholds,
    {
      candles: $("candles").checked,
      entries: $("entries").checked,
      start: startIndex(),
    },
  );
  // Preserve a user's zoom when only marker density or candle style changes.
  if (currentZoom)
    for (const zoom of option.dataZoom) {
      zoom.start = currentZoom.start;
      zoom.end = currentZoom.end;
      delete zoom.startValue;
      delete zoom.endValue;
    }
  chart.setOption(option, { notMerge: true });
  $("chart").setAttribute(
    "aria-label",
    `${selected.name}: adjusted price in ${selected.currency || "market currency"}, volume and RSI (14). Historical Buy/Sell circles are retrospective RSI conditions. Data as of ${selected.last_date}.`,
  );
}

function setRange(value) {
  range = value;
  document
    .querySelectorAll("[data-range]")
    .forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.range === range),
      ),
    );
  if (!chart || !dataset) return;
  chart.dispatchAction({
    type: "dataZoom",
    startValue: startIndex(),
    endValue: dataset.rows.length - 1,
  });
}

function table() {
  $("table-caption").textContent =
    `${selected.ticker} · ${selected.currency || "market currency"} · all completed historical sessions`;
  $("data-rows").replaceChildren(
    ...dataset.rows.map((row) => {
      const tr = document.createElement("tr");
      for (const value of [
        row[0],
        decimal(row[4]),
        compact(row[5]),
        row[6] == null ? "Unavailable" : row[6].toFixed(4),
        row[7] ? `RSI ${row[7]}` : "None",
      ]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      return tr;
    }),
  );
}

async function select(symbol, updateUrl = true) {
  const token = ++generation;
  pending?.abort();
  disposeChart();
  dataset = undefined;
  selected = manifest.securities.find(
    (item) => item.symbol === manifest.aliases[symbol.toUpperCase()],
  );
  $("download").disabled = true;
  $("unknown").hidden = Boolean(selected);
  $("security").hidden = !selected;
  $("status").textContent = "";
  renderList();
  if (!selected) {
    $("unknown-message").textContent =
      `“${symbol}” is not in this committed watchlist. Choose a security from the list.`;
    return;
  }
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set("ticker", selected.symbol);
    if (url.href !== window.location.href) history.pushState(null, "", url);
  }
  document.title = `${selected.ticker} · FinanceAlerts`;
  $("identity").textContent =
    `${selected.ticker} / ${selected.market} / ${selected.universe.replaceAll("_", " ")}`;
  $("company").textContent = selected.name;
  $("price").textContent = money(selected.close, selected.currency);
  $("rsi").textContent = selected.rsi == null ? "—" : selected.rsi.toFixed(2);
  $("technical").textContent = selected.condition;
  $("technical").className = conditionClass(selected.condition);
  $("asof").textContent = selected.last_date ?? "Unavailable";
  $("diagnostic").textContent = selected.diagnostic;
  $("diagnostic").hidden = !selected.diagnostic;
  $("chart").hidden =
    $("chart-controls").hidden =
    $("data-details").hidden =
      !selected.available;
  $("marker-note").textContent =
    `Green Buy circles: RSI ≤ ${manifest.thresholds.lower}. Red Sell circles: RSI ≥ ${manifest.thresholds.upper}. Retrospective RSI conditions only—not trades or historical Telegram deliveries. For short candidates, red circles identify a potential bearish setup; they do not establish put value.`;
  if (!selected.available) return;
  $("status").textContent = `Loading ${selected.ticker} chart…`;
  pending = new AbortController();
  try {
    const response = await fetch(new URL(selected.dataset, import.meta.url), {
      signal: pending.signal,
      cache: "no-cache",
    });
    if (!response.ok)
      throw new Error(
        "The dataset could not be loaded. Refresh to use the latest published snapshot.",
      );
    const data = await response.json();
    technicalRows(data);
    if (data.symbol !== selected.symbol)
      throw new Error(
        "The dataset identity does not match the selected security.",
      );
    if (generation !== token) return;
    dataset = data;
    if (!window.echarts)
      throw new Error(
        "The local chart library could not be loaded. Please reload this page.",
      );
    chart = window.echarts.init($("chart"), undefined, { renderer: "svg" });
    draw();
    setRange(range);
    observer = new ResizeObserver(() => chart?.resize());
    observer.observe($("chart"));
    table();
    $("download").disabled = false;
    $("status").textContent = "";
  } catch (error) {
    if (error.name === "AbortError" || generation !== token) return;
    disposeChart();
    $("status").textContent = `Chart unavailable: ${error.message}`;
  }
}

$("download").addEventListener("click", () => {
  if (!dataset) return;
  const csv =
    [
      dataset.columns.slice(0, 7).join(","),
      ...dataset.rows.map((row) =>
        row
          .slice(0, 7)
          .map((value) => value ?? "")
          .join(","),
      ),
    ].join("\n") + "\n";
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${selected.symbol}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
for (const id of ["search", "condition", "universe", "sort"])
  $(id).addEventListener(id === "search" ? "input" : "change", renderList);
for (const id of ["candles", "entries"]) $(id).addEventListener("change", draw);
document
  .querySelectorAll("[data-range]")
  .forEach((button) =>
    button.addEventListener("click", () => setRange(button.dataset.range)),
  );
$("return-list").addEventListener("click", () => {
  $("search").value = $("condition").value = $("universe").value = "";
  renderList();
  $("search").focus();
  select(manifest.securities[0].symbol);
});
window.addEventListener("popstate", () =>
  select(
    new URLSearchParams(location.search).get("ticker") ||
      manifest.securities[0].symbol,
    false,
  ),
);
window.addEventListener("pagehide", () => {
  pending?.abort();
  disposeChart();
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted && manifest)
    select(selected?.symbol || manifest.securities[0].symbol, false);
});

try {
  const response = await fetch(new URL("./manifest.json", import.meta.url), {
    cache: "no-cache",
  });
  if (!response.ok)
    throw new Error("The security manifest could not be loaded.");
  manifest = await response.json();
  if (!manifest.securities?.length)
    throw new Error("No monitored securities are published yet.");
  const available = manifest.securities.filter((item) => item.available).length;
  const stale = manifest.securities.filter((item) => item.stale).length;
  $("overview").textContent =
    `${manifest.securities.length} securities · ${available} with prices · ${stale} stale\nData as of ${manifest.data_as_of ?? "unavailable"}`;
  $("overview").style.whiteSpace = "pre-line";
  const ticker = new URLSearchParams(location.search).get("ticker");
  await select(
    ticker ||
      (
        manifest.securities.find((item) => item.available) ??
        manifest.securities[0]
      ).symbol,
    Boolean(ticker),
  );
} catch (error) {
  $("status").textContent =
    `Dashboard unavailable: ${error.message} Please reload or try again after the next publication.`;
}
