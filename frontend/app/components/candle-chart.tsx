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
        background: { type: ColorType.Solid, color: "#1b1f1a" },
        textColor: "#9b9588",
        fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "rgba(236, 226, 204, 0.06)" },
        horzLines: { color: "rgba(236, 226, 204, 0.06)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#e0b56a", width: 1, style: 3, labelBackgroundColor: "#2a261c" },
        horzLine: { color: "#e0b56a", width: 1, style: 3, labelBackgroundColor: "#2a261c" },
      },
      rightPriceScale: {
        borderColor: "rgba(236, 226, 204, 0.12)",
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "rgba(236, 226, 204, 0.12)",
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
      upColor: "#9dcc78",
      downColor: "#e08a80",
      borderUpColor: "#9dcc78",
      borderDownColor: "#e08a80",
      wickUpColor: "#9dcc78",
      wickDownColor: "#e08a80",
      priceLineVisible: true,
      lastValueVisible: true,
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "rgba(224, 181, 106, 0.28)",
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
      color: Number(bar.close) >= Number(bar.open) ? "rgba(157, 204, 120, 0.28)" : "rgba(224, 138, 128, 0.28)",
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
