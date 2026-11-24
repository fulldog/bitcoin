"use client";

import { useState } from "react";
import { CandleChart } from "./components/candle-chart";
import { State } from "./components/shell";
import { useApi } from "./lib/use-api";

type Summary = { mode: string; equity: string; daily_pnl: string; drawdown: string; open_orders: number; alerts: { code: string; severity?: string }[] };
type Realtime = { stream: string; symbol: string; price: string; closed_bars: number; connector: string; last_decision: string; llm_configured: boolean; llm_bias: string; llm_confidence: string; llm_reason: string; llm_model: string };
type Klines = { symbol: string; bars: { time: number; open: string; high: string; low: string; close: string }[] };
type Runs = { running: number; symbols: string[]; runs: { id: string; name: string; symbol: string; status: string; last_decision: string; signal_count: number; position: string; price: string; fast: number; slow: number; quote_amount: string }[] };

export default function OverviewPage() {
  const summary = useApi<Summary>("/api/dashboard/summary", 5000);
  const realtime = useApi<Realtime>("/api/realtime/status", 5000);
  const strategies = useApi<Runs>("/api/strategy-runs", 5000);
  const [symbol, setSymbol] = useState("");
  const chartSymbol = symbol || strategies.data?.symbols[0] || realtime.data?.symbol || "BTCUSDT";
  const candles = useApi<Klines>(`/api/klines?symbol=${chartSymbol}`, 5000);
  const market = realtime.data;
  const ready = market?.connector === "READY";
  return (
    <section className="page">
      <State loading={summary.loading} error={summary.error} />
      <article className="panel">
        <header>
          <h2>实时 K 线</h2>
          <div className="actions">
            {(strategies.data?.symbols ?? [chartSymbol]).map((item) => (
              <button className={item === chartSymbol ? "primary" : ""} key={item} type="button" onClick={() => setSymbol(item)}>{item}</button>
            ))}
          </div>
        </header>
        <CandleChart bars={candles.data?.bars ?? []} />
      </article>
      <article className="panel">
        <header><h2>运行中的策略</h2><span className="tag tag-ok">{strategies.data?.running ?? 0} 个</span></header>
        <div className="table-wrap">
          <table>
            <thead><tr><th>名称</th><th>币种</th><th>参数</th><th>价格</th><th>持仓</th><th>最近决策</th><th>信号</th></tr></thead>
            <tbody>
              {strategies.data?.runs.map((run) => (
                <tr key={run.id}>
                  <td>{run.name}</td>
                  <td>{run.symbol}</td>
                  <td>{run.fast}/{run.slow} · {run.quote_amount} USDT</td>
                  <td>{run.price}</td>
                  <td>{run.position}</td>
                  <td><span className="tag">{run.last_decision}</span></td>
                  <td>{run.signal_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {strategies.data && !strategies.data.runs.length && <p className="muted">还没有运行中的策略。到运行页创建后会自动开始。</p>}
      </article>
      <div className="banner-row">
        <article className="banner banner-green">
          <strong>行情连接</strong>
          <p>{market ? `${market.symbol} · ${market.stream}` : "等待行情"}</p>
        </article>
        <article className="banner banner-cyan">
          <strong>实盘状态</strong>
          <p>{summary.data?.mode ?? "LIVE"} · 未完成订单 {summary.data?.open_orders ?? 0}</p>
        </article>
        <article className="banner banner-violet">
          <strong>大模型参考</strong>
          <p>{market?.llm_configured ? market.llm_bias || "等待信号" : "未配置密钥"}</p>
        </article>
        <article className="banner banner-amber">
          <strong>风险告警</strong>
          <p>{summary.data?.alerts.length ? summary.data.alerts.map((alert) => alert.code).join("，") : "没有活动告警"}</p>
        </article>
      </div>
      <div className="split">
        <article className="panel">
          <header><h2>服务状态</h2></header>
          <ul className="status-list">
            <li><span>行情连接器</span><em className={ready ? "tag tag-ok" : "tag tag-warn"}>{market?.connector ?? "未知"}</em></li>
            <li><span>实时价格</span><strong>{market?.price ?? "--"}</strong></li>
            <li><span>闭合 K 线</span><strong>{market?.closed_bars ?? 0}</strong></li>
            <li><span>最近决策</span><em className="tag">{market?.last_decision || "无"}</em></li>
          </ul>
        </article>
        <article className="panel">
          <header><h2>大模型参考</h2><span className={market?.llm_configured ? "tag tag-ok" : "tag tag-off"}>{market?.llm_configured ? "已启用" : "未启用"}</span></header>
          <div className="table-wrap">
            <table>
              <caption className="muted">最近一次模型结论</caption>
              <thead><tr><th>模型</th><th>方向</th><th>置信度</th><th>说明</th></tr></thead>
              <tbody>
                <tr>
                  <td>{market?.llm_model || "--"}</td>
                  <td>{market?.llm_bias || "--"}</td>
                  <td>{market?.llm_confidence || "--"}</td>
                  <td>{market?.llm_reason || "配置 LLM_API_KEY 后生成参考"}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </div>
      {summary.data && (
        <div className="metric-row">
          <article className="metric"><span>净值</span><strong>{summary.data.equity}</strong><small>账户权益</small></article>
          <article className="metric"><span>当日盈亏</span><strong>{summary.data.daily_pnl}</strong><small>今日已实现变动</small></article>
          <article className="metric"><span>回撤</span><strong>{summary.data.drawdown}</strong><small>相对峰值</small></article>
          <article className="metric"><span>未完成订单</span><strong>{summary.data.open_orders}</strong><small>当前活动订单</small></article>
        </div>
      )}
    </section>
  );
}
