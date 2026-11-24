"use client";

import { State } from "./components/shell";
import { useApi } from "./lib/use-api";

type Summary = { mode: string; equity: string; daily_pnl: string; drawdown: string; open_orders: number; alerts: { code: string }[] };

export default function OverviewPage() {
  const summary = useApi<Summary>("/api/dashboard/summary", 5000);
  const state = <State loading={summary.loading} error={summary.error} />;
  return (
    <section>
      <h1>总览</h1>
      {state}
      {summary.data && (
        <div className="grid">
          <article className="card"><span>净值</span><strong>{summary.data.equity}</strong></article>
          <article className="card"><span>当日盈亏</span><strong>{summary.data.daily_pnl}</strong></article>
          <article className="card"><span>回撤</span><strong>{summary.data.drawdown}</strong></article>
          <article className="card"><span>未完成订单</span><strong>{summary.data.open_orders}</strong></article>
        </div>
      )}
    </section>
  );
}
