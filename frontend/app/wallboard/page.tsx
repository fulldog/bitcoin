"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Summary = {
  mode: string;
  equity: string;
  daily_pnl: string;
  drawdown: string;
  open_orders: number;
  alerts: { code: string; severity?: string }[];
  metrics: { heartbeat: string | null; reconciliation_diffs: number; rejects: number };
};

export default function WallboardPage() {
  const summary = useApi<Summary>("/api/dashboard/summary", 5000);
  return (
    <section className="wall" aria-label="交易大屏">
      <State loading={summary.loading} error={summary.error} />
      {summary.data && (
        <>
          <div className="metric-row">
            <article className="metric"><span>净值</span><strong>{summary.data.equity}</strong></article>
            <article className="metric"><span>当日盈亏</span><strong>{summary.data.daily_pnl}</strong></article>
            <article className="metric"><span>最大回撤</span><strong>{summary.data.drawdown}</strong></article>
            <article className="metric"><span>活动订单</span><strong>{summary.data.open_orders}</strong></article>
          </div>
          <aside className="panel">
            <header><h2>{summary.data.mode}</h2></header>
            <ul className="status-list">
              <li><span>心跳</span><strong>{summary.data.metrics.heartbeat ?? "未运行"}</strong></li>
              <li><span>拒单</span><strong>{summary.data.metrics.rejects}</strong></li>
              <li><span>对账差异</span><strong>{summary.data.metrics.reconciliation_diffs}</strong></li>
              <li><span>告警</span><em className="tag">{summary.data.alerts.length ? summary.data.alerts.map((alert) => alert.code).join("，") : "无"}</em></li>
            </ul>
          </aside>
        </>
      )}
    </section>
  );
}
