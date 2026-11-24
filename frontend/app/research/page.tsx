"use client";

import { FormEvent, useState } from "react";
import { State } from "../components/shell";
import { postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Strategies = { strategies: { name: string; version: string; parameters: Record<string, string | number> }[] };

export default function ResearchPage() {
  const strategies = useApi<Strategies>("/api/strategies");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const report = await postJson<{ id: string; fill_hash: string }>(`/api/backtests?dataset_id=${form.get("dataset")}`, {}, `research-${Date.now()}`);
      setResult(`${report.id.slice(0, 12)} / ${report.fill_hash.slice(0, 12)}`);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回测失败");
    }
  }

  return (
    <section className="page">
      <State loading={strategies.loading} error={strategies.error} empty={!strategies.data?.strategies.length} />
      <div className="split">
        <article className="panel">
          <header><h2>策略</h2></header>
          <div className="table-wrap">
            <table>
              <thead><tr><th>名称</th><th>版本</th><th>参数</th></tr></thead>
              <tbody>
                {strategies.data?.strategies.map((strategy) => (
                  <tr key={strategy.name}>
                    <td>{strategy.name}</td>
                    <td>{strategy.version}</td>
                    <td>{Object.entries(strategy.parameters).map(([key, value]) => `${key}=${value}`).join("，")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        <form className="research-edit" onSubmit={onSubmit}>
          <h2>运行回测</h2>
          <label htmlFor="dataset">数据集</label>
          <input id="dataset" name="dataset" defaultValue="btc" />
          <p className="muted">未导入该数据集时，使用当前连续的实时闭合 K 线。</p>
          <button type="submit">运行回测</button>
          {error && <p role="alert" className="danger">{error}</p>}
          {result && <p role="status">回测指纹：{result}</p>}
        </form>
      </div>
    </section>
  );
}
