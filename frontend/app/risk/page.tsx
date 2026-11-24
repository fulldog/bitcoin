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
    <section>
      <h1>风险</h1>
      <State loading={risk.loading} error={risk.error} />
      {risk.data && <p>就绪：{risk.data.ready ? "是" : "否"}；停止开关：{risk.data.kill_switch ? "已触发" : "未触发"}；数据缺口：{risk.data.data_gap ? "是" : "否"}。</p>}
      <button type="button" onClick={kill}>全局停止</button>
      {message && <p role="status">{message}</p>}
      <div className="table-wrap">
        <table>
          <caption>风控决定</caption>
          <thead><tr><th>代码</th><th>说明</th></tr></thead>
          <tbody>{risk.data?.decisions.map((item, index) => <tr key={`${item.code}-${index}`}><td>{item.code}</td><td>{item.message}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}
