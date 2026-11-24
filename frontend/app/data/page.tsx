"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Health = { connector: string; reconnects: number; datasets: { id: string; ready: boolean; digest: string }[] };

export default function DataPage() {
  const health = useApi<Health>("/api/data/health");
  return (
    <section className="page">
      <State loading={health.loading} error={health.error} empty={health.data?.datasets.length === 0} />
      {health.data && (
        <article className="panel">
          <header>
            <h2>已冻结数据集</h2>
            <span className={health.data.connector === "READY" ? "tag tag-ok" : "tag tag-warn"}>重连 {health.data.reconnects} 次</span>
          </header>
          <div className="table-wrap">
            <table>
              <thead><tr><th>数据集</th><th>状态</th><th>摘要</th></tr></thead>
              <tbody>
                {health.data.datasets.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td><span className={item.ready ? "tag tag-ok" : "tag tag-warn"}>{item.ready ? "可用" : "阻断"}</span></td>
                    <td>{item.digest.slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}
    </section>
  );
}
