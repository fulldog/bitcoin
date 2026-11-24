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
    <section>
      <h1>研究</h1>
      <State loading={strategies.loading} error={strategies.error} empty={!strategies.data?.strategies.length} />
      {strategies.data?.strategies.map((strategy) => (
        <article className="card" key={strategy.name}>
          <h2>{strategy.name} v{strategy.version}</h2>
          <p className="muted">{Object.entries(strategy.parameters).map(([key, value]) => `${key}=${value}`).join("，")}</p>
        </article>
      ))}
      <form className="research-edit stack" onSubmit={onSubmit}>
        <label htmlFor="dataset">数据集</label>
        <input id="dataset" name="dataset" defaultValue="btc" />
        <button type="submit">运行回测</button>
        {error && <p role="alert" className="danger">{error}</p>}
        {result && <p role="status">回测指纹：{result}</p>}
      </form>
    </section>
  );
}
