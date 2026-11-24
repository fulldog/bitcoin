"use client";

import { useState } from "react";
import { State } from "../components/shell";
import { getJson, postJson } from "../lib/api";
import { useApi } from "../lib/use-api";

type Status = { mode: string; runtime: string; connector: string };
type LlmReference = { configured: boolean; reference: { bias: string; confidence: string; reason: string; model: string } | null };
type StrategyRun = { id: string; name: string; symbol: string; status: string; fast: number; slow: number; quote_amount: string; price: string; position: string; last_decision: string; signal_count: number };
type StrategyList = { runs: StrategyRun[]; running: number };

let actionSerial = 0;

function actionKey(prefix: string) {
  actionSerial += 1;
  return `${prefix}-${actionSerial}`;
}

export default function RunsPage() {
  const status = useApi<Status>("/api/system/status", 5000);
  const reference = useApi<LlmReference>("/api/llm/reference", 5000);
  const [revision, setRevision] = useState(0);
  const strategies = useApi<StrategyList>(`/api/strategy-runs?refresh=${revision}`, 5000);
  const [message, setMessage] = useState("");
  const [closing, setClosing] = useState<StrategyRun | null>(null);
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
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "策略创建失败");
    }
  }

  async function startStrategy(run: StrategyRun) {
    try {
      await postJson(`/api/strategy-runs/${run.id}/start`, {}, actionKey(`start-${run.id}`));
      setMessage(`${run.name} 已启动`);
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "启动失败");
    }
  }

  async function confirmClose() {
    if (!closing) return;
    const run = closing;
    try {
      await postJson(`/api/strategy-runs/${run.id}/stop`, {}, actionKey(`stop-${run.id}`));
      setMessage(Number(run.position) > 0 ? `${run.name} 已关闭，持仓已市价卖出` : `${run.name} 已关闭`);
      setClosing(null);
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "关闭失败");
      setClosing(null);
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

  const selling = closing ? Number(closing.position) > 0 : false;

  return (
    <section className="page">
      <State loading={status.loading} error={status.error} />
      {message && <p className="notice" role="status">{message}</p>}
      <div className="readout-row">
        <article className="readout banner-green"><strong>运行时</strong><p>{status.data?.runtime ?? "读取中"}</p></article>
        <article className="readout banner-cyan"><strong>行情</strong><p>{status.data?.connector ?? "读取中"}</p></article>
        <article className="readout banner-violet"><strong>模型</strong><p>{reference.data?.reference ? `${reference.data.reference.bias} · ${reference.data.reference.confidence}` : "尚未生成参考"}</p></article>
        <article className="readout banner-amber"><strong>模式</strong><p>{status.data?.mode ?? "LIVE"}</p></article>
      </div>
      <article className="panel">
          <header>
            <h2>策略簿</h2>
            <span className={strategies.data?.running ? "tag tag-ok" : "tag tag-off"}>{strategies.data?.running ?? 0} 个运行中</span>
          </header>
          <State loading={strategies.loading} error={strategies.error} />
          <div className="table-wrap">
            <table>
              <thead><tr><th>名称</th><th>币种</th><th>状态</th><th>参数</th><th>价格</th><th>持仓</th><th>最近决策</th><th>操作</th></tr></thead>
              <tbody>
                {strategies.data?.runs.map((run) => (
                  <tr key={run.id}>
                    <td className="book-name">{run.name}</td>
                    <td className="num">{run.symbol}</td>
                    <td><span className={run.status === "running" ? "tag tag-ok" : "tag tag-off"}>{run.status === "running" ? "运行中" : "已关闭"}</span></td>
                    <td className="num">{run.fast}/{run.slow} · {run.quote_amount}</td>
                    <td className="num">{run.price}</td>
                    <td className="num">{run.position}</td>
                    <td>{run.last_decision}</td>
                    <td>
                      {run.status === "running"
                        ? <button className="danger-btn" type="button" onClick={() => setClosing(run)}>关闭</button>
                        : <button type="button" onClick={() => startStrategy(run)}>启动</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {strategies.data && !strategies.data.runs.length && <p className="empty">还没有策略。创建后会出现在这本策略簿里。</p>}
        </article>
      <div className="ops-layout">
          <article className="panel">
            <header><h2>新建策略</h2></header>
            <div className="field-grid">
              <div className="field">
                <label htmlFor="custom-symbol">币种</label>
                <input id="custom-symbol" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
              </div>
              <div className="field">
                <label htmlFor="strategy-name">策略名称</label>
                <input id="strategy-name" value={strategyName} onChange={(event) => setStrategyName(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="fast">快线</label>
                <input id="fast" value={fast} onChange={(event) => setFast(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="slow">慢线</label>
                <input id="slow" value={slow} onChange={(event) => setSlow(event.target.value)} />
              </div>
              <div className="field field-wide">
                <label htmlFor="quote">单次买入上限 USDT</label>
                <input id="quote" value={quote} onChange={(event) => setQuote(event.target.value)} />
              </div>
            </div>
            <div className="actions">
              <button type="button" onClick={addSymbol}>只订阅币种</button>
              <button className="primary" type="button" onClick={createStrategy}>创建并运行</button>
            </div>
          </article>
          <article className="panel panel-live">
            <header><h2>手动下单</h2></header>
            <div className="field-grid">
              <div className="field">
                <label htmlFor="side">方向</label>
                <select id="side" value={side} onChange={(event) => setSide(event.target.value)}>
                  <option value="BUY">买入</option>
                  <option value="SELL">卖出</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="quantity">BTC 数量</label>
                <input id="quantity" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
              </div>
              <div className="field field-wide">
                <label htmlFor="confirmation">实盘确认短语</label>
                <input id="confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
              </div>
            </div>
            <div className="actions">
              <button type="button" onClick={() => postJson("/api/live/unlock", { confirmation }, `unlock-${Date.now()}`).then(() => setMessage("实盘已解锁")).catch((reason: Error) => setMessage(reason.message))}>解锁实盘</button>
              <button type="button" onClick={account}>检查账户</button>
              <button type="button" onClick={askModel}>模型参考</button>
              <button type="button" onClick={() => command("pause")}>暂停</button>
              <button className="danger-solid" type="button" onClick={liveOrder}>提交市价单</button>
            </div>
            <p className="muted">需要 API Key、实盘开关和确认短语。配置大模型后，自动单还要和参考方向一致。</p>
            {reference.data?.reference && <p>参考说明：{reference.data.reference.reason}</p>}
          </article>
      </div>
      {closing && (
        <div className="modal-backdrop" onMouseDown={() => setClosing(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="close-strategy-title"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => { if (event.key === "Escape") setClosing(null); }}
          >
            <span className="eyebrow">Close position</span>
            <h2 id="close-strategy-title">关闭 {closing.name}</h2>
            <p>{selling ? `策略会立即停止，并把 ${closing.position} ${closing.symbol} 按市价卖出。` : "策略会立即停止。当前没有持仓，不会下单。"}</p>
            <div className="actions">
              <button type="button" autoFocus onClick={() => setClosing(null)}>取消</button>
              <button className={selling ? "danger-solid" : "primary"} type="button" onClick={confirmClose}>{selling ? "确认关闭并卖出" : "确认关闭"}</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
