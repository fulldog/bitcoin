"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Login } from "./login";
import { publishAuth, readToken, subscribeAuth } from "../lib/api";
import { useApi } from "../lib/use-api";

const links = [
  ["/", "总览"],
  ["/copy", "熬鹰"],
  ["/data", "数据"],
  ["/research", "研究"],
  ["/runs", "运行"],
  ["/orders", "订单"],
  ["/risk", "风险"],
  ["/logs", "日志"],
  ["/wallboard", "大屏"],
];

const titles: Record<string, string> = {
  "/": "控制台",
  "/copy": "熬鹰监控",
  "/data": "数据健康",
  "/research": "策略研究",
  "/runs": "实盘运行",
  "/orders": "订单成交",
  "/risk": "风险控制",
  "/logs": "系统日志",
  "/wallboard": "交易大屏",
};

type Status = { mode: string; runtime: string; connector: string };

export function Shell({ children }: { children: React.ReactNode }) {
  const token = useSyncExternalStore(subscribeAuth, readToken, () => null);
  if (!token) return <Login onSuccess={() => undefined} />;
  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}

function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const status = useApi<Status>("/api/system/status", 5000);
  const mode = status.data?.mode ?? "LIVE";
  const title = titles[pathname] ?? "控制台";
  return (
    <div className="shell">
      <aside className="sider">
        <div className="brand">
          <span className="logo">Q</span>
          <div>
            <strong>Quant</strong>
            <small>实盘控制台</small>
          </div>
        </div>
        <p className="nav-label">交易</p>
        <nav aria-label="主导航">
          {links.map(([href, label]) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link className={active ? "nav-link active" : "nav-link"} href={href} key={href}>
                <NavMark />
                {label}
              </Link>
            );
          })}
        </nav>
        <button className="logout" type="button" onClick={() => publishAuth(null)}>退出登录</button>
      </aside>
      <div className="workspace">
        <header className="pagebar">
          <h1>{title}</h1>
          <div className="userchip">
            <span className={status.data?.connector === "READY" ? "tag tag-ok" : "tag tag-warn"}>{status.data?.connector ?? "连接中"}</span>
            <span className="tag">{mode}</span>
            <span>xiongyk</span>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}

function NavMark() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <rect x="2" y="2" width="5" height="5" rx="1" fill="currentColor" />
      <rect x="9" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.45" />
      <rect x="2" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.45" />
      <rect x="9" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.75" />
    </svg>
  );
}

export function State({ loading, error, empty }: { loading: boolean; error: string; empty?: boolean }) {
  if (loading) return <p role="status">正在读取数据…</p>;
  if (error) return <p role="alert" className="danger">数据暂不可用：{error}</p>;
  if (empty) return <p role="status">当前没有记录。</p>;
  return null;
}
