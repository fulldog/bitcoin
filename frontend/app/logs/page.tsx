"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Logs = { logs: { event: string; type?: string; command_id?: number }[]; alerts: { severity: string; code: string }[] };

export default function LogsPage() {
  const logs = useApi<Logs>("/api/logs", 5000);
  return (
    <section>
      <h1>系统日志</h1>
      <State loading={logs.loading} error={logs.error} empty={!logs.data?.logs.length && !logs.data?.alerts.length} />
      <ul>
        {logs.data?.alerts.map((alert, index) => <li key={`${alert.code}-${index}`}>{alert.severity}：{alert.code}</li>)}
        {logs.data?.logs.map((entry, index) => <li key={`${entry.event}-${index}`}>{entry.event} {entry.type} {entry.command_id ?? ""}</li>)}
      </ul>
    </section>
  );
}
