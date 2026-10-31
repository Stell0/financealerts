import { test, expect } from "@playwright/test";

const thresholds = { lower: 30, upper: 70 };
const values = [null, 29, 30, 31, 69, 70, 75, null, 29, 29, 50, 70];
const rows = values.map((rsi, i) => {
  const signal =
    rsi == null ? null : rsi <= 30 ? "Buy" : rsi >= 70 ? "Sell" : null;
  const previous =
    values[i - 1] == null
      ? null
      : values[i - 1] <= 30
        ? "Buy"
        : values[i - 1] >= 70
          ? "Sell"
          : null;
  return [
    `2026-10-${String(i + 1).padStart(2, "0")}`,
    100 + i,
    103 + i,
    98 + i,
    101 + i,
    1000 + i,
    rsi,
    signal,
    signal != null && signal !== previous,
  ];
});
const columns = [
  "Date",
  "Open",
  "High",
  "Low",
  "Close",
  "Volume",
  "RSI",
  "Signal",
  "Entry",
];
const securities = [
  ["NVDA", "NVIDIA", "long", 70],
  ["TSLA", "Tesla", "long", 29],
  ["0981.HK", "SMIC", "long", 50],
  ["BTC-USD", "Bitcoin", "long", 75],
  ["FCEL", "FuelCell Energy", "short", 75],
  ["KSCP", "Knightscope", "research_only", null],
].map(([symbol, name, universe, rsi]) => ({
  symbol,
  ticker: symbol === "BTC-USD" ? "BTCUSD" : symbol,
  name,
  universe,
  rsi,
  market: "XNAS",
  currency: "USD",
  available: symbol !== "KSCP",
  stale: false,
  condition:
    rsi == null
      ? "Unavailable"
      : rsi <= 30
        ? "Oversold"
        : rsi >= 70
          ? "Overbought"
          : "Neutral",
  close: 112,
  last_date: symbol === "KSCP" ? null : "2026-10-12",
  dataset: `data/${symbol}.json`,
  diagnostic:
    symbol === "KSCP"
      ? "No committed price cache. Awaiting a successful daily scan."
      : "",
}));

async function fixture(page) {
  await page.route("**/manifest.json", (route) =>
    route.fulfill({
      json: {
        version: 1,
        thresholds,
        data_as_of: "2026-10-12",
        securities,
        aliases: Object.fromEntries([
          ...securities.map((item) => [item.symbol, item.symbol]),
          ["BTCUSD", "BTC-USD"],
        ]),
      },
    }),
  );
  await page.route("**/data/*.json", (route) => {
    const symbol = decodeURIComponent(
      new URL(route.request().url()).pathname.split("/").at(-1).slice(0, -5),
    );
    return route.fulfill({ json: { symbol, columns, rows } });
  });
}

const option = (page) =>
  page.evaluate(() =>
    window.echarts
      .getInstanceByDom(document.getElementById("chart"))
      .getOption(),
  );

test("committed NVDA data renders a real chart lazily under the Pages subpath", async ({
  page,
}) => {
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  const requests = [];
  page.on("request", (request) => {
    if (/\/data\/.*\.json/.test(request.url())) requests.push(request.url());
  });
  await page.goto("?ticker=NVDA");
  await expect(page.locator("#chart svg")).toBeVisible();
  await expect(page.locator("#identity")).toContainText("NVDA");
  const data = await option(page);
  expect(data.series[0].data.length).toBeGreaterThan(100);
  expect(data.series[3].type).toBe("bar");
  expect(data.series[4].data.length).toBe(data.series[0].data.length);
  expect(data.xAxis).toHaveLength(3);
  expect(data.axisPointer[0].link[0].xAxisIndex).toEqual([0, 1, 2]);
  expect(requests).toHaveLength(1);
  await page.goto("?ticker=GOOGL");
  await expect(page.locator("#chart svg")).toBeVisible();
  await expect(page.locator("#identity")).toContainText("GOOG /");
  await expect(page).toHaveURL(/ticker=GOOG$/);
  await page.goto("?ticker=BTCUSD");
  await expect(page.locator("#chart svg")).toBeVisible();
  await expect(page).toHaveURL(/ticker=BTC-USD$/);
  await page.goto("about:blank");
  await page.goBack();
  await expect(page.locator("#chart svg")).toBeVisible();
  expect(failures).toEqual([]);
});

test("historical circles render, align, expose a shared tooltip and filter first entries", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("?ticker=NVDA");
  await expect(page.locator("#chart svg")).toBeVisible();
  let data = await option(page);
  expect(data.series[1].type).toBe("scatter");
  expect(data.series[1].symbolSize).toBe(8);
  expect(data.series[1].itemStyle.color).toBe("#16834b");
  expect(data.series[2].itemStyle.color).toBe("#cf3b46");
  expect(data.series[1].data).toEqual(
    rows
      .filter((row) => row[7] === "Buy")
      .map((row) => [row[0], row[4], row[6], row[7]]),
  );
  expect(data.series[2].data).toHaveLength(3);
  // Verify real rendered SVG marker paths, not merely a stored option or HTML text.
  await expect(page.locator('#chart svg path[fill="#16834b"]')).not.toHaveCount(
    0,
  );
  await expect(page.locator('#chart svg path[fill="#cf3b46"]')).not.toHaveCount(
    0,
  );
  await page.evaluate(() =>
    window.echarts
      .getInstanceByDom(document.getElementById("chart"))
      .dispatchAction({ type: "showTip", seriesIndex: 1, dataIndex: 0 }),
  );
  await expect(page.locator("#chart")).toContainText("2026-10-02");
  await expect(page.locator("#chart")).toContainText("RSI (14): 29.00");
  await expect(page.locator("#chart")).toContainText(
    "Historical RSI condition: Buy",
  );
  await page.getByLabel("First entry only").check();
  data = await option(page);
  expect(data.series[1].data).toHaveLength(2);
  expect(data.series[2].data).toHaveLength(2);
  await page.getByLabel("Candlesticks").check();
  expect((await option(page)).series[0].type).toBe("candlestick");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe("NVDA.csv");
});

test("search, condition and universe filters, RSI sorting and quick selection", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("?ticker=NVDA");
  await expect(page.locator("#chart svg")).toBeVisible();
  await page.getByLabel("Find a security").fill("Tesla");
  await expect(page.locator(".security-row")).toHaveCount(1);
  await page.locator(".security-row").click();
  await expect(page).toHaveURL(/ticker=TSLA/);
  await expect(page.locator("#company")).toHaveText("Tesla");
  await expect(page.locator("#chart svg")).toHaveCount(1);
  await page.getByLabel("Find a security").fill("");
  await page
    .getByLabel("Condition", { exact: true })
    .selectOption("Overbought");
  await expect(page.locator(".security-row")).toHaveCount(3);
  await page.getByLabel("Universe", { exact: true }).selectOption("short");
  await expect(page.locator(".security-row")).toHaveCount(1);
  await page.getByLabel("Universe", { exact: true }).selectOption("");
  await page.getByLabel("Condition", { exact: true }).selectOption("");
  await page.getByLabel("Sort by").selectOption("rsi-asc");
  await expect(page.locator(".security-row").first()).toHaveAttribute(
    "data-symbol",
    "TSLA",
  );
  await expect(page.locator(".security-row").last()).toHaveAttribute(
    "data-symbol",
    "KSCP",
  );
  await page.getByLabel("Sort by").selectOption("rsi-desc");
  await expect(page.locator(".security-row").first()).toHaveAttribute(
    "data-symbol",
    "BTC-USD",
  );
});

test("direct dot/hyphen aliases, reload, back navigation and friendly unknown handling", async ({
  page,
}) => {
  await fixture(page);
  for (const [query, canonical] of [
    ["0981.HK", "0981.HK"],
    ["BTCUSD", "BTC-USD"],
    ["BTC-USD", "BTC-USD"],
  ]) {
    await page.goto(`?ticker=${encodeURIComponent(query)}`);
    await expect(page.locator("#chart svg")).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`ticker=${canonical.replaceAll(".", "\\.")}`),
    );
    await page.reload();
    await expect(page.locator("#identity")).toContainText(
      canonical === "BTC-USD" ? "BTCUSD" : canonical,
    );
  }
  await page.goto("?ticker=%3Cscript%3Ebad%3C%2Fscript%3E");
  await expect(
    page.getByRole("heading", { name: "Security not found" }),
  ).toBeVisible();
  await expect(page.locator("#chart svg")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Return to the security list" })
    .click();
  await expect(page.locator("#chart svg")).toBeVisible();
  await page.locator('[data-symbol="FCEL"]').click();
  await expect(page).toHaveURL(/ticker=FCEL/);
  await page.goBack();
  await expect(page.locator("#identity")).toContainText("NVDA");
});

test("zoom links all panels, mobile resize works and reduced motion is respected", async ({
  page,
}) => {
  await fixture(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("?ticker=NVDA");
  await expect(page.locator("#chart svg")).toBeVisible();
  const width = await page
    .locator("#chart svg")
    .evaluate((element) => element.getBoundingClientRect().width);
  expect(width).toBeGreaterThan(250);
  expect(width).toBeLessThan(390);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() =>
    window.echarts
      .getInstanceByDom(document.getElementById("chart"))
      .dispatchAction({ type: "dataZoom", startValue: 3, endValue: 8 }),
  );
  const data = await option(page);
  expect(data.animation).toBe(false);
  for (const zoom of data.dataZoom) expect(zoom.xAxisIndex).toEqual([0, 1, 2]);
  const extents = await page.evaluate(() => {
    const chart = window.echarts.getInstanceByDom(
      document.getElementById("chart"),
    );
    return [0, 1, 2].map((index) =>
      chart.getModel().getComponent("xAxis", index).axis.scale.getExtent(),
    );
  });
  expect(extents[0]).toEqual(extents[1]);
  expect(extents[1]).toEqual(extents[2]);
  expect(extents[0]).toEqual([3, 8]);
  await page.getByRole("button", { name: "All", exact: true }).click();
  expect((await option(page)).dataZoom[0].startValue).toBe(0);
  await page.locator('[data-symbol="KSCP"]').click();
  await expect(page.locator("#diagnostic")).toContainText(
    "No committed price cache",
  );
  await expect(page.locator("#chart svg")).toHaveCount(0);
});

test("dataset errors remain visible and another security can still render", async ({
  page,
}) => {
  await fixture(page);
  await page.route("**/data/NVDA.json", (route) =>
    route.fulfill({ status: 404 }),
  );
  await page.goto("?ticker=NVDA");
  await expect(page.locator("#status")).toContainText("Chart unavailable");
  await page.locator('[data-symbol="TSLA"]').click();
  await expect(page.locator("#chart svg")).toBeVisible();
  await expect(page.locator("#status")).toBeEmpty();
});
