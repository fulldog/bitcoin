"use client";

import { FormEvent, useState } from "react";
import { login } from "../lib/api";

export function Login({ onSuccess = () => undefined }: { onSuccess?: () => void }) {
  const [username, setUsername] = useState("xiongyk");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await login(username, password);
      onSuccess();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    }
  }

  return (
    <main className="login">
      <form onSubmit={submit}>
        <div className="brand">
          <span className="logo">Q</span>
          <div>
            <strong>Quant</strong>
            <small>实盘控制台</small>
          </div>
        </div>
        <h1>登录</h1>
        <label htmlFor="username">账号</label>
        <input id="username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        <label htmlFor="password">密码</label>
        <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        {error && <p role="alert" className="danger">{error}</p>}
        <button type="submit">进入控制台</button>
      </form>
    </main>
  );
}
