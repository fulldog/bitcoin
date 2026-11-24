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
          <div className="grid">
            <article className="card"><span>净值</span><strong>{summary.data.equity}</strong></article>
            <article className="card"><span>当日盈亏</span><strong>{summary.data.daily_pnl}</strong></article>
            <article className="card"><span>最大回撤</span><strong>{summary.data.drawdown}</strong></article>
            <article className="card"><span>活动订单</span><strong>{summary.data.open_orders}</strong></article>
          </div>
          <aside className="card">
            <h1>{summary.data.mode}</h1>
            <p>心跳：{summary.data.metrics.heartbeat ?? "未运行"}</p>
            <p>拒单：{summary.data.metrics.rejects}</p>
            <p>对账差异：{summary.data.metrics.reconciliation_diffs}</p>
            <p>{summary.data.alerts.length ? summary.data.alerts.map((alert) => alert.code).join("，") : "没有活动告警"}</p>
          </aside>
        </>
      )}
    </section>
  );
}
