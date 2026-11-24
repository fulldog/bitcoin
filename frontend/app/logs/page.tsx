"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Logs = { logs: { event: string; type?: string; command_id?: number }[]; alerts: { severity: string; code: string }[] };

export default function LogsPage() {
  const logs = useApi<Logs>("/api/logs", 5000);
  const rows = [
    ...(logs.data?.alerts.map((alert) => ({ kind: alert.severity, name: alert.code, detail: "" })) ?? []),
    ...(logs.data?.logs.map((entry) => ({ kind: entry.event, name: entry.type ?? "", detail: entry.command_id ? String(entry.command_id) : "" })) ?? []),
  ];
  return (
    <section className="page">
      <State loading={logs.loading} error={logs.error} empty={!rows.length} />
      <article className="panel">
        <header><h2>日志与告警</h2></header>
        <div className="table-wrap">
          <table>
            <thead><tr><th>类型</th><th>名称</th><th>编号</th></tr></thead>
            <tbody>{rows.map((row, index) => <tr key={`${row.kind}-${row.name}-${index}`}><td><span className="tag">{row.kind}</span></td><td>{row.name}</td><td>{row.detail}</td></tr>)}</tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
