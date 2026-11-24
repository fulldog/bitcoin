"use client";

import { FormEvent, useState } from "react";
import { State } from "../components/shell";
import { postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Strategies = { strategies: { name: string; version: string; parameters: Record<string, string | number> }[] };
type T1Report = { day: string; bars: number; dataset_id: string; fill_hash: string; metrics: Record<string, string | number> };

let researchSerial = 0;

function researchKey(prefix: string) {
  researchSerial += 1;
  return `${prefix}-${researchSerial}`;
}

export default function ResearchPage() {
  const strategies = useApi<Strategies>("/api/strategies");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1h");
  const [t1, setT1] = useState<T1Report | null>(null);
  const [t1Error, setT1Error] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const report = await postJson<{ id: string; fill_hash: string }>(`/api/backtests?dataset_id=${form.get("dataset")}`, {}, researchKey("research"));
      setResult(`${report.id.slice(0, 12)} / ${report.fill_hash.slice(0, 12)}`);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回测失败");
    }
  }

  async function runPreviousDay() {
    try {
      const report = await postJson<T1Report>("/api/research/t1", { symbol, interval }, researchKey("t1"));
      setT1(report);
      setT1Error("");
    } catch (reason) {
      setT1(null);
      setT1Error(reason instanceof Error ? reason.message : "昨日回测失败");
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
        <article className="panel">
          <header><h2>昨日行情</h2></header>
          <div className="field-grid">
            <div className="field">
              <label htmlFor="t1-symbol">币种</label>
              <input id="t1-symbol" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
            </div>
            <div className="field">
              <label htmlFor="t1-interval">周期</label>
              <select id="t1-interval" value={interval} onChange={(event) => setInterval(event.target.value)}>
                <option value="15m">15 分钟</option>
                <option value="1h">1 小时</option>
                <option value="4h">4 小时</option>
              </select>
            </div>
          </div>
          <div className="actions">
            <button className="primary" type="button" onClick={runPreviousDay}>用昨日收盘数据回测</button>
          </div>
          <p className="muted">直接读取 Binance 上一个 UTC 日的闭合 K 线，不需要下载文件。行情不连续时会拒绝回测。</p>
          {t1Error && <p role="alert" className="danger">{t1Error}</p>}
          {t1 && (
            <div className="stack">
              <p role="status">{t1.day} · {t1.bars} 根 · {t1.dataset_id}</p>
              <ul className="status-list">
                {Object.entries(t1.metrics).map(([key, value]) => <li key={key}><span>{key}</span><strong className="num">{String(value)}</strong></li>)}
              </ul>
            </div>
          )}
        </article>
    </section>
  );
}
