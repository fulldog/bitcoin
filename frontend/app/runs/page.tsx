"use client";

import { useState } from "react";
import { State } from "../components/shell";
import { getJson, postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Status = { mode: string; runtime: string; connector: string };
type LlmReference = { configured: boolean; reference: { bias: string; confidence: string; reason: string; model: string } | null };

export default function RunsPage() {
  const status = useApi<Status>("/api/system/status", 5000);
  const reference = useApi<LlmReference>("/api/llm/reference", 5000);
  const [message, setMessage] = useState("");
  const [side, setSide] = useState("BUY");
  const [quantity, setQuantity] = useState("0.001");
  const [confirmation, setConfirmation] = useState("");
  const [symbol, setSymbol] = useState("ETHUSDT");
  const [strategyName, setStrategyName] = useState("趋势策略");
  const [fast, setFast] = useState("2");
  const [slow, setSlow] = useState("3");
  const [quote, setQuote] = useState("90");

  async function addSymbol() {
    try {
      await postJson("/api/symbols", { symbol }, `symbol-${Date.now()}`);
      setMessage(`${symbol.toUpperCase()} 已加入行情订阅`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "添加币种失败");
    }
  }

  async function createStrategy() {
    try {
      const created = await postJson<{ name: string; symbol: string }>("/api/strategy-runs", { name: strategyName, symbol, fast: Number(fast), slow: Number(slow), quote_amount: quote }, `strategy-${Date.now()}`);
      setMessage(`${created.name} 已启动，正在接收 ${created.symbol}`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "策略创建失败");
    }
  }

  async function command(type: "pause" | "kill") {
    const result = await postJson<{ command_id: number }>("/api/commands", { type, cash: "1000" }, `${type}-${Date.now()}`);
    await postJson("/api/runtime/process", {}, `process-${Date.now()}`);
    setMessage(`${type} 已提交，命令 ${result.command_id}`);
  }

  async function account() {
    try {
      const body = await getJson<{ can_trade: boolean }>("/api/binance/account");
      setMessage(`Binance 已连接，可交易：${body.can_trade}`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Binance 连接失败");
    }
  }

  async function askModel() {
    try {
      const body = await postJson<{ bias: string; confidence: string; reason: string }>("/api/llm/reference", {}, `llm-${Date.now()}`);
      setMessage(`大模型参考 ${body.bias}，置信度 ${body.confidence}。${body.reason}`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "大模型参考失败");
    }
  }

  async function liveOrder() {
    try {
      const result = await postJson<{ status: string }>("/api/live/orders", { symbol: "BTCUSDT", side, quantity, confirmation }, `live-${Date.now()}`);
      setMessage(`实盘订单状态 ${result.status}`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "实盘下单失败");
    }
  }

  return (
    <section className="page">
      <State loading={status.loading} error={status.error} />
      <div className="banner-row">
        <article className="banner banner-green"><strong>运行时</strong><p>{status.data?.runtime ?? "读取中"}</p></article>
        <article className="banner banner-cyan"><strong>行情</strong><p>{status.data?.connector ?? "读取中"}</p></article>
        <article className="banner banner-violet"><strong>模型</strong><p>{reference.data?.reference ? `${reference.data.reference.bias} · ${reference.data.reference.confidence}` : "尚未生成参考"}</p></article>
        <article className="banner banner-amber"><strong>模式</strong><p>{status.data?.mode ?? "LIVE"}</p></article>
      </div>
      <article className="panel">
        <header><h2>自定义币种和策略</h2></header>
        <div className="form-grid">
          <label htmlFor="custom-symbol">币种</label>
          <input id="custom-symbol" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
          <label htmlFor="strategy-name">策略名称</label>
          <input id="strategy-name" value={strategyName} onChange={(event) => setStrategyName(event.target.value)} />
          <label htmlFor="fast">快线</label>
          <input id="fast" value={fast} onChange={(event) => setFast(event.target.value)} />
          <label htmlFor="slow">慢线</label>
          <input id="slow" value={slow} onChange={(event) => setSlow(event.target.value)} />
          <label htmlFor="quote">单次买入上限 USDT</label>
          <input id="quote" value={quote} onChange={(event) => setQuote(event.target.value)} />
        </div>
        <div className="actions">
          <button type="button" onClick={addSymbol}>添加币种</button>
          <button className="primary" type="button" onClick={createStrategy}>创建并运行策略</button>
        </div>
      </article>
      <article className="panel">
        <header><h2>实盘操作</h2></header>
        <div className="form-grid">
          <label htmlFor="side">方向</label>
          <select id="side" value={side} onChange={(event) => setSide(event.target.value)}>
            <option value="BUY">买入</option>
            <option value="SELL">卖出</option>
          </select>
          <label htmlFor="quantity">BTC 数量</label>
          <input id="quantity" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
          <label htmlFor="confirmation">实盘确认短语</label>
          <input id="confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
        </div>
        <div className="actions">
          <button type="button" onClick={() => command("pause")}>暂停</button>
          <button type="button" onClick={() => postJson("/api/live/unlock", { confirmation }, `unlock-${Date.now()}`).then(() => setMessage("实盘已解锁")).catch((reason: Error) => setMessage(reason.message))}>解锁实盘</button>
          <button type="button" onClick={askModel}>获取大模型参考</button>
          <button type="button" onClick={account}>检查 Binance 账户</button>
          <button className="primary" type="button" onClick={liveOrder}>提交实盘市价单</button>
        </div>
        <p className="muted">实盘需要 API Key、LIVE_BUILD_ENABLED、LIVE_TRADING_ENABLED 和确认短语。配置 LLM_API_KEY 后，自动下单还要和大模型参考方向一致。</p>
        {reference.data?.reference && <p>参考说明：{reference.data.reference.reason}</p>}
        {message && <p role="status">{message}</p>}
      </article>
    </section>
  );
}
