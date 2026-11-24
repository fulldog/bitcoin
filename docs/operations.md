# 运行与事故处理

## 环境

生产或实盘使用 PostgreSQL 与 Redis。SQLite 只用于本地测试。复制 `.env.example` 为 `.env`，不要把 `.env` 提交到仓库。

实盘解锁必须同时满足：

- `LIVE_BUILD_ENABLED=true`
- `LIVE_TRADING_ENABLED=true`
- `TRADING_MODE=live`
- 请求提供与 `LIVE_CONFIRMATION_PHRASE` 完全一致的确认短语

缺少任意一项时，系统保持锁定。首次灰度只使用白名单交易对和极小的单笔、单日限额。

## 启动与验收

```powershell
docker compose up --build
```

验收顺序固定为：历史回测指纹可复现、模拟盘可暂停和恢复、Binance Spot Testnet 完成下单与对账、最后才是小额实盘。Testnet 可能重置数据，只用于验证执行，不用于评估收益。

手动 Testnet 检查不在常规测试中运行。常规测试使用录制或伪造的交易所响应。

## 备份与恢复

- 备份 PostgreSQL 中的 K 线、订单、成交、审计事件和运行快照。
- Redis 只保存队列、缓存和通知，不作为交易事实来源。
- 恢复时先导入数据库，再启动 runtime。runtime 必须重放快照之后的事件，并向交易所对账后才能进入 `READY`。
- 对账差异产生告警，不能仅凭本地缓存继续交易。

## 密钥轮换

1. 在交易所创建新的只读或交易密钥，禁用提现并设置 IP 白名单。
2. 替换服务端环境变量或本机 secret。
3. 重启 API 与 runtime。
4. 撤销旧密钥。日志只记录脱敏后的字段。

## 全局停止

风险页面的“全局停止”会提交 `kill` 命令。runtime 处理后拒绝新订单，并保留可审计的风控决定。事故回滚时先触发全局停止，再撤销交易所上仍可撤销的挂单，最后保留数据库备份。

## 常见故障

- 行情缺口、乱序、重复或未闭合 K 线：连接器保持 `NOT_READY`。
- 请求明确未发出：允许安全重试。
- 超时或不确定的 5xx：订单进入 `UNKNOWN`，先查询客户端订单 ID。
- PostgreSQL 或 Redis 不可用：阻断新交易，已持久化的审计记录不回滚为猜测状态。
