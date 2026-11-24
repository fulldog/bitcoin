"use client";

import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  HistogramSeries,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

type Candle = { time: number; open: string; high: string; low: string; close: string; volume?: string };

export function CandleChart({ bars }: { bars: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const barsRef = useRef(bars);
  const rangeRef = useRef("");
  const [hovered, setHovered] = useState<Candle | null>(null);

  useEffect(() => {
    barsRef.current = bars;
  }, [bars]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#667085",
        fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "#eef1f6" },
        horzLines: { color: "#eef1f6" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#98a2b3", width: 1, style: 3, labelBackgroundColor: "#344054" },
        horzLine: { color: "#98a2b3", width: 1, style: 3, labelBackgroundColor: "#344054" },
      },
      rightPriceScale: {
        borderColor: "#e6eaf2",
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "#e6eaf2",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        barSpacing: 8,
        minBarSpacing: 3,
      },
      localization: {
        timeFormatter: (time: Time) => {
          const timestamp = typeof time === "number" ? time : 0;
          return new Date(timestamp * 1000).toLocaleString("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          });
        },
      },
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#17803d",
      downColor: "#c2414b",
      borderUpColor: "#17803d",
      borderDownColor: "#c2414b",
      wickUpColor: "#17803d",
      wickDownColor: "#c2414b",
      priceLineVisible: true,
      lastValueVisible: true,
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "rgba(59, 102, 245, 0.20)",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    const handleCrosshair = (param: MouseEventParams<Time>) => {
      if (!param.time || !param.seriesData) {
        setHovered(null);
        return;
      }
      const data = param.seriesData.get(candleSeries);
      if (!data || !("open" in data)) {
        setHovered(null);
        return;
      }
      const candle = barsRef.current.find((bar) => bar.time === Number(param.time));
      setHovered(candle ?? null);
    };
    chart.subscribeCrosshairMove(handleCrosshair);
    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshair);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const chart = chartRef.current;
    if (!candleSeries || !volumeSeries || !chart) return;
    const sorted = [...bars]
      .filter((bar) => Number.isFinite(Number(bar.time)))
      .sort((a, b) => a.time - b.time)
      .filter((bar, index, all) => index === 0 || bar.time !== all[index - 1].time);
    const candleData: CandlestickData<UTCTimestamp>[] = sorted.map((bar) => ({
      time: bar.time as UTCTimestamp,
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
    }));
    candleSeries.setData(candleData);
    volumeSeries.setData(sorted.map((bar) => ({
      time: bar.time as UTCTimestamp,
      value: Number(bar.volume ?? 0),
      color: Number(bar.close) >= Number(bar.open) ? "rgba(23, 128, 61, 0.22)" : "rgba(194, 65, 75, 0.22)",
    })));
    const range = sorted.length ? `${sorted[0].time}:${sorted[sorted.length - 1].time}` : "";
    if (range && range !== rangeRef.current) {
      chart.timeScale().fitContent();
      rangeRef.current = range;
    }
  }, [bars]);

  return (
    <div className="chart-shell">
      <div className="chart-toolbar">
        <span>{bars.length ? `${bars.length} 根 · 1 分钟` : "等待行情数据"}</span>
        {hovered && (
          <span className="chart-ohlc">
            {new Date(hovered.time * 1000).toLocaleString("zh-CN", { hour12: false })} ·
            开 {hovered.open} · 高 {hovered.high} · 低 {hovered.low} · 收 {hovered.close}
          </span>
        )}
      </div>
      <div ref={containerRef} className="chart" role="img" aria-label="实时 K 线图" />
      {!bars.length && <div className="chart-empty" role="status">正在加载历史 K 线…</div>}
    </div>
  );
}
