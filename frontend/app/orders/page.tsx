"use client";

import { State } from "../components/shell";
import { useApi } from "../lib/use-api";

type Orders = { orders: { client_order_id?: string; symbol?: string; status?: string; quantity?: string }[] };
type Fills = { fills: { client_order_id: string; symbol: string; price: string; quantity: string }[] };

export default function OrdersPage() {
  const orders = useApi<Orders>("/api/orders", 5000);
  const fills = useApi<Fills>("/api/fills", 5000);
  return (
    <section className="stack">
      <h1>订单与成交</h1>
      <State loading={orders.loading || fills.loading} error={orders.error || fills.error} empty={!orders.data?.orders.length && !fills.data?.fills.length} />
      <div className="table-wrap">
        <table>
          <caption>订单</caption>
          <thead><tr><th>编号</th><th>交易对</th><th>状态</th><th>数量</th></tr></thead>
          <tbody>{orders.data?.orders.map((order) => <tr key={order.client_order_id}><td>{order.client_order_id}</td><td>{order.symbol}</td><td>{order.status}</td><td>{order.quantity}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}
