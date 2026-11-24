"use client";

import { useState } from "react";
import { State } from "../components/shell";
import { postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Profile = { username: string; role: string };
type Users = { users: { username: string; role: string; created_at: string }[] };

export default function UsersPage() {
  const profile = useApi<Profile>("/api/auth/me");
  const users = useApi<Users>("/api/users");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const admin = profile.data?.role === "admin";

  async function createUser() {
    try {
      const created = await postJson<{ username: string }>("/api/users", { username, password }, `user-${Date.now()}`);
      setMessage(`${created.username} 已创建，可以使用新账号登录`);
      setUsername("");
      setPassword("");
      window.location.reload();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "创建用户失败");
    }
  }

  return (
    <section className="page">
      <State loading={profile.loading || users.loading} error={profile.error || (admin ? users.error : "")} />
      <article className="panel">
        <header><h2>新增用户</h2><span className={admin ? "tag tag-ok" : "tag tag-off"}>{admin ? "管理员" : "普通用户"}</span></header>
        {admin ? (
          <>
            <div className="form-grid">
              <label htmlFor="new-username">用户名</label>
              <input id="new-username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" />
              <label htmlFor="new-password">密码</label>
              <input id="new-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
            </div>
            <div className="actions">
              <button className="primary" type="button" onClick={createUser}>创建用户</button>
            </div>
          </>
        ) : <p>当前账号不能新增用户。</p>}
        <p className="muted">每个用户拥有独立的币种、策略、订单、回测和实盘状态。交易所 API Key 仍由服务器统一配置。用户会保留，策略数据在 API 重启后清空。</p>
        {message && <p role="status">{message}</p>}
      </article>
      {admin && (
        <article className="panel">
          <header><h2>用户列表</h2></header>
          <div className="table-wrap">
            <table>
              <thead><tr><th>用户名</th><th>角色</th><th>创建时间</th></tr></thead>
              <tbody>
                {users.data?.users.map((user) => (
                  <tr key={user.username}>
                    <td>{user.username}</td>
                    <td>{user.role === "admin" ? "管理员" : "用户"}</td>
                    <td>{new Date(user.created_at).toLocaleString("zh-CN", { hour12: false })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}
    </section>
  );
}
