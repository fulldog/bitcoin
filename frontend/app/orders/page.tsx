"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Orders = { orders: { client_order_id?: string; symbol?: string; status?: string; quantity?: string }[] };
type Fills = { fills: { client_order_id: string; symbol: string; price: string; quantity: string }[] };

export default function OrdersPage() {
  const orders = useApi<Orders>("/api/orders", 5000);
  const fills = useApi<Fills>("/api/fills", 5000);
  return (
    <section className="page">
      <State loading={orders.loading || fills.loading} error={orders.error || fills.error} empty={!orders.data?.orders.length && !fills.data?.fills.length} />
      <article className="panel">
        <header><h2>订单</h2></header>
        <div className="table-wrap">
          <table>
            <thead><tr><th>编号</th><th>交易对</th><th>状态</th><th>数量</th></tr></thead>
            <tbody>{orders.data?.orders.map((order) => <tr key={order.client_order_id}><td>{order.client_order_id}</td><td>{order.symbol}</td><td><span className="tag">{order.status}</span></td><td>{order.quantity}</td></tr>)}</tbody>
          </table>
        </div>
      </article>
      <article className="panel">
        <header><h2>成交</h2></header>
        <div className="table-wrap">
          <table>
            <thead><tr><th>编号</th><th>交易对</th><th>价格</th><th>数量</th></tr></thead>
            <tbody>{fills.data?.fills.map((fill) => <tr key={fill.client_order_id}><td>{fill.client_order_id}</td><td>{fill.symbol}</td><td>{fill.price}</td><td>{fill.quantity}</td></tr>)}</tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
