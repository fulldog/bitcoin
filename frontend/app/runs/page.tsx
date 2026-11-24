"use client";

import { useState } from "react";
import { State } from "../components/shell";
import { postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Status = { mode: string; runtime: string; connector: string };

export default function RunsPage() {
  const status = useApi<Status>("/api/system/status", 5000);
  const [message, setMessage] = useState("");

  async function command(type: "start_paper" | "pause" | "kill") {
    const result = await postJson<{ command_id: number }>("/api/commands", { type, cash: "1000" }, `${type}-${Date.now()}`);
    await postJson("/api/runtime/process", {}, `process-${Date.now()}`);
    setMessage(`${type} 已提交，命令 ${result.command_id}`);
  }

  return (
    <section>
      <h1>模拟与实盘运行</h1>
      <State loading={status.loading} error={status.error} />
      {status.data && <p>模式 {status.data.mode}，运行时 {status.data.runtime}，行情 {status.data.connector}。</p>}
      <div className="stack">
        <button type="button" onClick={() => command("start_paper")}>启动模拟盘</button>
        <button type="button" onClick={() => command("pause")}>暂停</button>
        <p className="muted">实盘解锁保留在服务端，需要构建开关、环境开关和确认短语。</p>
        {message && <p role="status">{message}</p>}
      </div>
    </section>
  );
}
