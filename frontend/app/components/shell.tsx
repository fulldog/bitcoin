"use client";

import Link from "next/link";
import { useApi } from "../lib/use-api";

const links = [
  ["/", "总览"],
  ["/data", "数据"],
  ["/research", "研究"],
  ["/runs", "运行"],
  ["/orders", "订单"],
  ["/risk", "风险"],
  ["/logs", "日志"],
  ["/wallboard", "大屏"],
];

type Status = { mode: string; runtime: string; connector: string };

export function Shell({ children }: { children: React.ReactNode }) {
  const status = useApi<Status>("/api/system/status", 5000);
  const mode = status.data?.mode ?? "PAPER";
  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Personal Quant</p>
          <Link href="/">交易控制台</Link>
        </div>
        <strong className={`mode mode-${mode.toLowerCase()}`} aria-live="polite">
          {mode}
        </strong>
        <nav aria-label="主导航">
          {links.map(([href, label]) => (
            <Link key={href} href={href}>{label}</Link>
          ))}
        </nav>
      </header>
      <main>{children}</main>
    </div>
  );
}

export function State({ loading, error, empty }: { loading: boolean; error: string; empty?: boolean }) {
  if (loading) return <p role="status">正在读取数据…</p>;
  if (error) return <p role="alert" className="danger">数据暂不可用：{error}</p>;
  if (empty) return <p role="status">当前没有记录。</p>;
  return null;
}
