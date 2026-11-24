"use client";

import { useState } from "react";
import { State } from "../components/shell";
import { postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Risk = { kill_switch: boolean; ready: boolean; data_gap?: boolean; decisions: { code: string; message: string }[] };

export default function RiskPage() {
  const risk = useApi<Risk>("/api/risk", 5000);
  const [message, setMessage] = useState("");

  async function kill() {
    await postJson("/api/commands", { type: "kill" }, `kill-${Date.now()}`);
    await postJson("/api/runtime/process", {}, `kill-process-${Date.now()}`);
    setMessage("全局停止已提交。");
  }

  return (
    <section className="page">
      <State loading={risk.loading} error={risk.error} />
      <div className="banner-row">
        <article className="banner banner-green"><strong>就绪</strong><p>{risk.data?.ready ? "是" : "否"}</p></article>
        <article className="banner banner-amber"><strong>停止开关</strong><p>{risk.data?.kill_switch ? "已触发" : "未触发"}</p></article>
        <article className="banner banner-cyan"><strong>数据缺口</strong><p>{risk.data?.data_gap ? "是" : "否"}</p></article>
        <article className="banner banner-violet"><strong>决定数</strong><p>{risk.data?.decisions.length ?? 0}</p></article>
      </div>
      <article className="panel">
        <header>
          <h2>风控决定</h2>
          <button className="danger-btn" type="button" onClick={kill}>全局停止</button>
        </header>
        {message && <p role="status">{message}</p>}
        <div className="table-wrap">
          <table>
            <thead><tr><th>代码</th><th>说明</th></tr></thead>
            <tbody>{risk.data?.decisions.map((item, index) => <tr key={`${item.code}-${index}`}><td>{item.code}</td><td>{item.message}</td></tr>)}</tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
