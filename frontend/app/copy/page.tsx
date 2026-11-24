"use client";

import { useState } from "react";
import { State } from "../components/shell";
import { postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Position = { symbol: string; side: string; size: string; entry_price: string; mark_price: string; leverage: string; margin_mode: string; pnl: string; roi: string };
type History = { symbol: string; side: string; leverage: string; entry_price: string; close_price: string; pnl: string; roi: string; opened: number; closed: number; margin_mode: string };
type Profile = {
  nickname: string;
  description: string;
  status: string;
  profile_url: string;
  positions_public: boolean;
  aum: string;
  margin_balance: string;
  copier_pnl: string;
  profit_share: string;
  copy_count: number;
  max_copy_count: number;
  total_copy_count: number;
  min_copy_usd: number;
  sharpe: string;
  roi: string;
  pnl: string;
  mdd: string;
  win_rate: string;
  tags: string[];
  positions: Position[];
  history: History[];
};

function money(value: string | number | undefined): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "--";
  return amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function clock(value: number): string {
  if (!value) return "--";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export default function CopyPage() {
  const profile = useApi<Profile>("/api/copy/aoying", 15000);
  const [amount, setAmount] = useState("100");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const data = profile.data;

  async function copyNow() {
    try {
      const result = await postJson<{ orders: { symbol: string; side: string; status: string; reason?: string }[] }>("/api/copy/aoying", { quote_amount: amount, confirmation }, `aoying-${Date.now()}`);
      setMessage(result.orders.map((item) => `${item.symbol} ${item.side} ${item.status}${item.reason ? ` ${item.reason}` : ""}`).join("；"));
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "跟单失败");
    }
  }

  return (
    <section className="page">
      <State loading={profile.loading} error={profile.error} />
      {data && (
        <>
          <div className="banner-row">
            <article className="banner banner-green"><strong>{data.nickname}</strong><p>{data.status} · 跟单 {data.copy_count}/{data.max_copy_count}</p></article>
            <article className="banner banner-cyan"><strong>30 日收益</strong><p>{money(data.roi)}% · 盈亏 {money(data.pnl)}</p></article>
            <article className="banner banner-violet"><strong>带单规模</strong><p>AUM {money(data.aum)} · 保证金 {money(data.margin_balance)}</p></article>
            <article className="banner banner-amber"><strong>风险</strong><p>回撤 {money(data.mdd)}% · 胜率 {money(data.win_rate)}%</p></article>
          </div>
          <article className="panel">
            <header>
              <h2>公开账户</h2>
              <a href={data.profile_url} target="_blank" rel="noreferrer">币安带单页</a>
            </header>
            <p>{data.description}</p>
            <div className="actions">
              {data.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
              <span className="tag">夏普 {money(data.sharpe)}</span>
              <span className="tag">分润 {money(data.profit_share)}%</span>
              <span className="tag">最低跟单 {money(data.min_copy_usd)} USDT</span>
              <span className="tag">历史跟单 {data.total_copy_count}</span>
            </div>
            <p className="muted">跟单者盈亏 {money(data.copier_pnl)} USDT。这里只读取币安公开带单数据，不读取对方私有账户。</p>
          </article>
          <article className="panel">
            <header>
              <h2>当前持仓</h2>
              <span className={data.positions_public ? "tag tag-ok" : "tag tag-warn"}>{data.positions_public ? "已公开" : "未公开"}</span>
            </header>
            {data.positions_public ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>合约</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>杠杆</th><th>保证金</th><th>收益</th></tr></thead>
                  <tbody>
                    {data.positions.map((item) => (
                      <tr key={`${item.symbol}-${item.side}`}>
                        <td>{item.symbol}</td><td>{item.side}</td><td>{item.size}</td><td>{item.entry_price}</td><td>{item.mark_price}</td><td>{item.leverage}</td><td>{item.margin_mode}</td><td>{item.pnl}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p>带单员关闭了当前持仓展示。系统不会猜测隐藏仓位。</p>}
            {data.positions_public && !data.positions.length && <p className="muted">当前没有公开持仓。</p>}
          </article>
          <article className="panel">
            <header><h2>一键跟单</h2></header>
            <div className="form-grid">
              <label htmlFor="copy-amount">跟单名义金额 USDT</label>
              <input id="copy-amount" value={amount} onChange={(event) => setAmount(event.target.value)} />
              <label htmlFor="copy-confirmation">实盘确认短语</label>
              <input id="copy-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
            </div>
            <div className="actions">
              <button className="primary" type="button" disabled={!data.positions_public || !data.positions.length} onClick={copyNow}>一键跟单</button>
            </div>
            <p className="muted">点击后按当前公开持仓的名义价值比例，在你自己的 U 本位合约账户开仓。杠杆固定为 1 倍，总名义金额不超过输入值和系统单笔上限。需要 API Key、实盘开关和确认短语。</p>
            {message && <p role="status">{message}</p>}
          </article>
          <article className="panel">
            <header><h2>最近平仓</h2></header>
            <div className="table-wrap">
              <table>
                <thead><tr><th>合约</th><th>方向</th><th>杠杆</th><th>开仓价</th><th>平仓价</th><th>盈亏</th><th>收益率</th><th>开仓时间</th><th>平仓时间</th></tr></thead>
                <tbody>
                  {data.history.map((item) => (
                    <tr key={`${item.symbol}-${item.opened}`}>
                      <td>{item.symbol}</td><td>{item.side}</td><td>{item.leverage}</td><td>{item.entry_price}</td><td>{item.close_price}</td><td>{money(item.pnl)}</td><td>{money(Number(item.roi) * 100)}%</td><td>{clock(item.opened)}</td><td>{clock(item.closed)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </>
      )}
    </section>
  );
}
