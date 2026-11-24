"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Health = { connector: string; reconnects: number; datasets: { id: string; ready: boolean; digest: string }[] };

export default function DataPage() {
  const health = useApi<Health>("/api/data/health");
  return (
    <section>
      <h1>数据健康</h1>
      <State loading={health.loading} error={health.error} empty={health.data?.datasets.length === 0} />
      {health.data && (
        <>
          <p>连接器状态：{health.data.connector}，重连 {health.data.reconnects} 次。</p>
          <div className="table-wrap">
            <table>
              <caption>已冻结数据集</caption>
              <thead><tr><th>数据集</th><th>可用</th><th>摘要</th></tr></thead>
              <tbody>
                {health.data.datasets.map((item) => (
                  <tr key={item.id}><td>{item.id}</td><td>{item.ready ? "可用" : "阻断"}</td><td>{item.digest.slice(0, 12)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
