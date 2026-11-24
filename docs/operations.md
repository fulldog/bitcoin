# 运行与事故处理

## 环境

复制 `.env.example` 为 `.env`，不要提交 `.env`。本地测试可以使用 SQLite；Docker Compose 部署使用 PostgreSQL 和 Redis。Redis 只保存短期任务和通知，订单、成交、余额和审计事件以 PostgreSQL 为准。

启动前确认：

- `AUTH_PASSWORD` 和 `JWT_SECRET` 已替换，JWT 密钥不少于 32 字节。
- `REALTIME_SYMBOL` 与 `REALTIME_INTERVAL` 符合预期。
- 实盘 Key 未开启提现权限，并已设置 IP 白名单。
- 使用大模型参考时填写 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`。接口需要兼容 OpenAI Chat Completions。留空 `LLM_API_KEY` 表示不启用。
- 合约跟单使用 `BINANCE_FUTURES_BASE_URL`，默认 `https://fapi.binance.com`。现货与合约共用同一组 API Key，但权限必须分别开通。

## 实盘解锁

以下条件必须同时成立，否则 `POST /api/live/orders` 返回 403 或 409：

- `LIVE_BUILD_ENABLED=true`
- `LIVE_TRADING_ENABLED=true`
- 请求中的确认短语等于 `LIVE_CONFIRMATION_PHRASE`
- 已有实时价格、实时连接正常且 Kill Switch 未触发
- 订单通过数量步长、最小名义金额、单笔限额和余额检查

首次使用只选择一个白名单交易对，并把 `MAX_ORDER_NOTIONAL` 与 `MAX_DAILY_LOSS` 保持在可承受范围内。

## 自定义策略与行情

`POST /api/symbols` 和 `POST /api/strategy-runs` 都需要 JWT 与 `Idempotency-Key`。交易对必须匹配 `[A-Z0-9]{5,20}`，快线周期必须小于慢线。策略、币种和 K 线缓存位于 API 进程内存中；发布或重启后要重新添加，不能把重启前的内存状态当作已持久化的交易记录。

K 线接口失败时返回 502。本地已有缓存时继续返回缓存，不把外部请求失败伪装成空行情。

## 熬鹰跟单

跟单读取币安公开接口，不保存对方账户凭证，也不访问隐藏持仓。启用前确认：

- API Key 具备 U 本位合约交易权限，并且没有提现权限。
- 合约账户使用单向持仓。跟单订单不发送 `positionSide`。
- `MAX_ORDER_NOTIONAL` 是单次跟单总名义金额上限。
- 跟单会把对应合约杠杆设置为 1 倍，这会改变该合约的账户杠杆设置。
- 持仓未公开时按钮保持禁用，接口返回 409。

跟单请求同样需要确认短语、实盘开关和幂等键。单个合约下单失败会记为 `FAILED`，已经提交的合约不会自动回滚。发生异常时先在 Binance 核对真实持仓，再决定是否手动平仓。

## 启动与验收

```powershell
docker compose up --build
```

没有 Docker 时，分别启动后端 `python -m uvicorn app.main:app --reload` 和前端 `npm run dev`。

验收顺序：

1. 登录控制台并确认未登录请求返回 401。
2. 导入固定数据集，重复回测得到相同成交指纹。
3. 实时行情能够重连，缺口或乱序时连接器保持 `NOT_READY`。
4. 实盘保持锁定，全局停止可以生效。
5. 使用 Binance Spot Testnet 完成账户查询、下单、撤单、超时查询和重启对账。
6. 最后才切换生产地址并进行小额实盘。

常规测试使用伪造的交易所响应。手动 Testnet 或生产检查不能放入自动测试。

## 备份与恢复

- 备份 PostgreSQL 中的 K 线、订单、成交、审计事件和运行快照。
- 恢复时先导入数据库，再启动 API 与 runtime。
- runtime 重放快照之后的事件，并与 Binance 的未完成订单和账户余额对账。
- 对账不一致时保持非就绪状态，不能仅凭本地缓存继续下单。

## 密钥轮换

1. 在 Binance 创建新的读取、现货和所需合约交易密钥，禁用提现并设置 IP 白名单。
2. 替换服务端 `BINANCE_API_KEY` 和 `BINANCE_API_SECRET`。
3. 重启 API 与 runtime。
4. 调用 `GET /api/binance/account` 确认连接。
5. 撤销旧密钥。日志不得记录密钥、签名或完整敏感请求。

## 全局停止

风险或运行页面触发 `kill` 后，需要再调用 `POST /api/runtime/process` 处理命令。系统随后拒绝新的实盘订单。事故处理顺序：

1. 触发全局停止。
2. 在 Binance 撤销仍可撤销的挂单。
3. 核对账户余额、持仓和本地订单。
4. 保留数据库备份，确认原因后再重新解锁。

## 常见故障

- 行情缺口、乱序、重复或未闭合 K 线：连接器保持 `NOT_READY`，不继续交易。
- Binance Key 缺失：账户查询和下单返回 409。
- 请求明确没有发出：可以使用新的幂等键安全重试。
- 超时或不确定的服务端错误：先按客户端订单号查询，禁止立即重新提交同一笔订单。
- PostgreSQL 或 Redis 不可用：阻断新交易，不把缺失记录猜测为成功或失败。
