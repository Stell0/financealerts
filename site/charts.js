// Adapted from PaperTrader pre-research-only-20261018 technicalRows/technicalOption.
// Three category grids share dates, crosshairs and both zoom controls; no Quartz.
export const compact = (value) =>
  new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
export const decimal = (value) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en", { maximumFractionDigits: 4 }).format(value);

export function technicalRows(dataset) {
  const required = [
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
  if (
    !Array.isArray(dataset.rows) ||
    !dataset.rows.length ||
    JSON.stringify(dataset.columns) !== JSON.stringify(required) ||
    dataset.rows.some((row) => row.length !== required.length)
  ) {
    throw new Error("The price dataset is empty or misaligned.");
  }
  return { rows: dataset.rows, dates: dataset.rows.map((row) => row[0]) };
}

export function technicalOption(
  dataset,
  currency,
  thresholds,
  { candles = false, entries = false, start = 0 } = {},
) {
  const { rows, dates } = technicalRows(dataset);
  const tooltip = (params) => {
    const point = Array.isArray(params) ? params[0] : params;
    const date = point.axisValue ?? point.value?.[0];
    const row = rows[dates.indexOf(date)];
    if (!row) return "";
    return `${date}\nAdjusted close: ${decimal(row[4])} ${currency}\nVolume: ${compact(row[5])}\nRSI (14): ${row[6] == null ? "Unavailable" : row[6].toFixed(2)}\nHistorical RSI condition: ${row[7] ?? "None"}`;
  };
  const markers = (signal) =>
    rows
      .filter((row) => row[7] === signal && (!entries || row[8]))
      .map((row) => [row[0], row[4], row[6], row[7]]);
  return {
    aria: {
      enabled: true,
      description: `Adjusted ${currency} prices, volume and RSI. Green circles: retrospective RSI Buy conditions; red circles: retrospective RSI Sell conditions. Not executed trades.`,
    },
    animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    textStyle: { fontFamily: "system-ui, sans-serif" },
    tooltip: {
      trigger: "axis",
      renderMode: "richText",
      confine: true,
      formatter: tooltip,
      backgroundColor: "#152435",
      textStyle: { color: "#f6f8fc", fontSize: 11 },
    },
    axisPointer: {
      link: [{ xAxisIndex: [0, 1, 2] }],
      lineStyle: { color: "#8b9cb1", type: "dashed" },
    },
    legend: {
      top: 9,
      left: 52,
      itemWidth: 9,
      itemHeight: 9,
      textStyle: { fontSize: 10, color: "#627182" },
      data: [
        "Adjusted price",
        `Buy · RSI ≤ ${thresholds.lower}`,
        `Sell · RSI ≥ ${thresholds.upper}`,
      ],
    },
    grid: [
      { left: 59, right: 24, top: "11%", height: "40%" },
      { left: 59, right: 24, top: "58%", height: "11%" },
      { left: 59, right: 24, top: "76%", height: "14%" },
    ],
    xAxis: [0, 1, 2].map((index) => ({
      type: "category",
      gridIndex: index,
      data: dates,
      boundaryGap: true,
      axisLabel: {
        show: index === 2,
        hideOverlap: true,
        fontSize: 10,
        color: "#7b899b",
        formatter: (value) => value.slice(5),
      },
      axisTick: { show: false },
      axisLine: { show: false },
      axisPointer: { label: { show: true } },
    })),
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        name: currency || "Price",
        axisLabel: { formatter: compact },
      },
      {
        type: "value",
        gridIndex: 1,
        min: 0,
        name: "Volume",
        axisLabel: { formatter: compact },
      },
      {
        type: "value",
        gridIndex: 2,
        min: 0,
        max: 100,
        interval: 50,
        name: "RSI (14)",
      },
    ].map((axis) => ({
      ...axis,
      nameTextStyle: { fontSize: 10, color: "#7b899b", align: "left" },
      axisLabel: { fontSize: 10, color: "#7b899b", ...axis.axisLabel },
      splitLine: { lineStyle: { color: "#eef1f5" } },
    })),
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: [0, 1, 2],
        startValue: start,
        endValue: dates.length - 1,
        filterMode: "filter",
      },
      {
        type: "slider",
        xAxisIndex: [0, 1, 2],
        startValue: start,
        endValue: dates.length - 1,
        bottom: 4,
        height: 18,
        filterMode: "filter",
        borderColor: "#e3e9f0",
        fillerColor: "#285ad51a",
        handleStyle: { color: "#285ad5" },
        textStyle: { fontSize: 9 },
      },
    ],
    series: [
      {
        name: "Adjusted price",
        type: candles ? "candlestick" : "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.8, color: "#285ad5" },
        itemStyle: candles
          ? {
              color: "#16834b",
              color0: "#cf3b46",
              borderColor: "#16834b",
              borderColor0: "#cf3b46",
            }
          : { color: "#285ad5" },
        data: candles
          ? rows.map((row) => [row[1], row[4], row[3], row[2]])
          : rows.map((row) => row[4]),
        z: 2,
      },
      ...["Buy", "Sell"].map((signal) => ({
        name: `${signal} · RSI ${signal === "Buy" ? "≤ " + thresholds.lower : "≥ " + thresholds.upper}`,
        type: "scatter",
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: "circle",
        symbolSize: 8,
        z: 6,
        itemStyle: {
          color: signal === "Buy" ? "#16834b" : "#cf3b46",
          borderColor: "white",
          borderWidth: 1,
          opacity: 1,
        },
        data: markers(signal),
        tooltip: { trigger: "item", formatter: tooltip },
      })),
      {
        name: "Volume",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: rows.map((row) => ({
          value: row[5],
          itemStyle: {
            color: row[4] >= row[1] ? "#96b7cb" : "#c5a3aa",
            opacity: 0.8,
          },
        })),
      },
      {
        name: "RSI (14)",
        type: "line",
        xAxisIndex: 2,
        yAxisIndex: 2,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color: "#8a65bb", width: 1.6 },
        itemStyle: { color: "#8a65bb" },
        data: rows.map((row) => row[6]),
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#aab5c4", type: "dashed", width: 1 },
          label: { formatter: "{c}", fontSize: 9 },
          data: [{ yAxis: thresholds.lower }, { yAxis: thresholds.upper }],
        },
        markArea: {
          silent: true,
          data: [
            [
              { yAxis: 0, itemStyle: { color: "#16834b09" } },
              { yAxis: thresholds.lower },
            ],
            [
              { yAxis: thresholds.upper, itemStyle: { color: "#cf3b4609" } },
              { yAxis: 100 },
            ],
          ],
        },
      },
    ],
  };
}
