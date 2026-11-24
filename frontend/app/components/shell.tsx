"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Login } from "./login";
import { publishAuth, readToken, subscribeAuth } from "../lib/api";
import { useApi } from "../lib/use-api";

const groups = [
  { label: "MARKET", links: [["/", "总览"], ["/copy", "熬鹰"], ["/data", "数据"]] },
  { label: "TRADE", links: [["/runs", "运行"], ["/orders", "订单"], ["/risk", "风险"]] },
  { label: "SYSTEM", links: [["/research", "研究"], ["/logs", "日志"], ["/users", "用户"], ["/wallboard", "大屏"]] },
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
  "/users": "用户管理",
  "/wallboard": "交易大屏",
};

type Profile = { username: string; role: string };

type Status = { mode: string; runtime: string; connector: string };

export function Shell({ children }: { children: React.ReactNode }) {
  const token = useSyncExternalStore(subscribeAuth, readToken, () => null);
  if (!token) return <Login onSuccess={() => undefined} />;
  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}

function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const status = useApi<Status>("/api/system/status", 5000);
  const profile = useApi<Profile>("/api/auth/me");
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
        <nav aria-label="主导航">
          {groups.map((group) => (
            <div key={group.label}>
              <p className="nav-label">{group.label}</p>
              {group.links.map(([href, label]) => {
                const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
                return (
                  <Link className={active ? "nav-link active" : "nav-link"} href={href} key={href}>
                    {label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sider-foot">
          <span>{profile.data?.username ?? "用户"}</span>
          <button className="logout" type="button" onClick={() => publishAuth(null)}>退出登录</button>
        </div>
      </aside>
      <div className="workspace">
        <header className="pagebar">
          <div>
            <span className="eyebrow">Quant · Live</span>
            <h1>{title}</h1>
          </div>
          <div className="userchip">
            <span className={status.data?.connector === "READY" ? "tag tag-ok" : "tag tag-warn"}>{status.data?.connector ?? "连接中"}</span>
            <span className="tag">{mode}</span>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}

export function State({ loading, error, empty }: { loading: boolean; error: string; empty?: boolean }) {
  if (loading) return <p role="status">正在读取数据…</p>;
  if (error) return <p role="alert" className="danger">数据暂不可用：{error}</p>;
  if (empty) return <p role="status">当前没有记录。</p>;
  return null;
}
