# 个人加密货币量化平台

面向 Binance 现货的个人研究、回测和实盘控制台。交易只走实盘，实盘开关默认关闭。

## 功能

- JWT 登录保护全部业务接口。管理员可以新增用户，每个用户有独立的策略和订单记录。
- 导入闭合 K 线、检查重复、乱序、缺口和未闭合数据。
- 对冻结数据集运行 SMA 交叉策略，生成可复现的成交指纹、前视偏差和 walk-forward 结果。
- 订阅 Binance 公开 K 线，只把闭合 K 线送入实盘策略分析。
- 添加自定义交易对，创建 SMA 策略后立即接收该交易对行情。策略可以随时启动或关闭；关闭时确认后按市价卖出该策略持仓。
- 总览使用 TradingView Lightweight Charts 展示历史和实时 K 线。
- 调用兼容 OpenAI 接口的大模型，生成买入、卖出或观望参考。
- 通过官方签名接口查询账户并提交现货市价单。
- 读取币安公开带单资料，并在持仓公开时按自有资金一键跟单。
- 研究页可以直接读取 Binance 上一个 UTC 日的闭合 K 线并回测。
- 配置 API Key 后，每分钟用交易所余额核对本地策略持仓；本地持仓更多时禁止新的买入。
- 总览、熬鹰、数据、研究、运行、订单、风险、日志、用户和大屏页面。

## 本地启动

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest
python -m app.store.migrate
python -m uvicorn app.main:app --reload

cd ..\frontend
npm install
npm run dev
```

- 控制台：<http://localhost:3000>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/healthz>

复制 `.env.example` 为 `.env`。默认登录账号是 `xiongyk`，初始密码见 `AUTH_PASSWORD`。部署前更换 `AUTH_PASSWORD` 和 `JWT_SECRET`，JWT 默认有效 12 小时。

后端测试使用内存 SQLite 和伪造的交易所响应，不访问 Binance，也不发送真实订单。本地运行不需要 Docker、PostgreSQL 或 Redis。`docker-compose.yml` 里的 PostgreSQL、Redis、worker 和 runtime 仍是预留服务，当前 API 不连接它们。

## 数据库

当前数据库是 **SQLite**，通过 SQLAlchemy 2 访问。默认连接串是：

```text
sqlite+aiosqlite:///./quant.db
```

API 启动时把它转换成同步驱动 `sqlite+pysqlite`。从 `backend` 目录启动时，库文件是 `backend/quant.db`。`python -m app.store.migrate` 会创建交易表；用户表在 API 进程启动时创建。不需要单独安装数据库服务。

| 表 | 内容 | 重启后 |
| --- | --- | --- |
| `users` | 用户名、密码哈希、角色 | 保留 |
| `strategy_states` | 策略参数、状态、持仓数量、成本 | 保留 |
| `live_orders` | 实盘订单状态 | 保留 |
| `fill_ledger` | 实盘成交 | 保留 |
| `candles` | 导入的 K 线 | 保留 |
| `audit_events` | 审计事件 | 保留 |

以下内容仍只在 API 进程内存中，重启后消失：实时 K 线缓存、回测报告、实盘解锁状态、幂等键和未发出的策略信号。策略本身会按用户恢复，并继续订阅对应交易对。

Binance API Key 不入库，只从环境变量读取。所有用户共用这一组服务端密钥，因此真实订单进入同一个交易所账户。用户之间隔离的是控制台里的策略、订单和页面数据。

## 页面

| 路径 | 用途 |
| --- | --- |
| `/` | 实时 K 线、运行策略、净值与连接状态 |
| `/copy` | 熬鹰公开带单监控和一键跟单 |
| `/data` | 数据集与行情健康 |
| `/research` | 策略和回测 |
| `/runs` | 自定义币种、策略、实盘解锁和下单 |
| `/orders` | 本地订单与成交 |
| `/risk` | 风控状态 |
| `/logs` | 命令和告警 |
| `/users` | 管理员新增用户 |
| `/wallboard` | 只读大屏 |

## 实时行情

`REALTIME_ENABLED=true` 时，API 启动后连接：

```text
wss://stream.binance.com:9443/ws/btcusdt@kline_1m
```

`REALTIME_SYMBOL` 和 `REALTIME_INTERVAL` 设置启动时的默认交易对与周期。公开行情不需要 API Key。`GET /api/klines?symbol=BTCUSDT` 在本地历史不足 100 根时，向 Binance REST 拉取最近 180 根闭合 K 线，并与后续 WebSocket 数据合并。前端图表提供价格轴、时间轴、网格、当前价格、成交量和十字光标。

运行页通过 `POST /api/symbols` 添加交易对，通过 `POST /api/strategy-runs` 创建 SMA 策略。策略创建后状态为 `running`，只处理自己的交易对。`POST /api/strategy-runs/{id}/start` 重新启动，`POST /api/strategy-runs/{id}/stop` 在确认后关闭；有持仓时先提交现货市价卖出，全部成交后才记为已关闭。总览只汇总仍在运行的策略。策略记录写入 SQLite，实时 K 线缓存仍在内存中。

系统忽略未闭合 K 线，检查闭合 K 线的顺序和缺口，然后运行 SMA 策略。账户资金不少于单次买入上限时，实际买入金额取上限的 90%，并至少保留 1 USDT。持仓后下跌 2% 止损；盈利达到 1.5% 后，止损跟随最高价下移 0.5%。止盈随持仓时间下降：开仓即 3%，15 根 K 线后 1.5%，30 根后只要不亏损就退出。连续两次止损后，15 根 K 线内不再开新仓。订单在发往交易所前先记为 CREATED，失败记为 FAILED，超时记为 UNKNOWN 后再查询。配置 `LLM_API_KEY` 后，自动下单前会把最近 30 根收盘价发给大模型。只有模型参考方向和策略信号一致时，订单才会继续送往 Binance。模型不可用或方向不一致时，该信号不会自动下单。断线后按指数退避重连。实时行情状态位于 `GET /api/realtime/status`。

## 研究流程

1. 使用 `POST /api/datasets` 导入闭合 K 线。重复、乱序、缺口或未闭合 K 线会使数据集不可交易。
2. 使用 `POST /api/backtests?dataset_id=...` 运行 SMA 交叉策略。同一数据集和参数必须得到相同成交指纹。
3. 研究页也可以调用 `POST /api/research/t1`，直接读取 Binance 上一个 UTC 日的闭合 K 线。不需要下载文件。行情不连续时返回 409。
4. 查看回测假设、前视偏差检查和 walk-forward 结果。
5. 在运行页解锁实盘并检查账户。连接器未就绪、账户未对账或未解锁时，运行时拒绝新的交易意图。

所有变更请求都需要 `Idempotency-Key` 请求头和 `Authorization: Bearer <token>`。

## 实盘交易

实盘下单调用 Binance 现货 `POST /api/v3/order`。下单前必须同时满足：

- `BINANCE_BASE_URL=https://api.binance.com`
- `BINANCE_API_KEY` 与 `BINANCE_API_SECRET` 已配置
- `LIVE_BUILD_ENABLED=true`
- `LIVE_TRADING_ENABLED=true`
- 确认短语与 `LIVE_CONFIRMATION_PHRASE` 完全一致，默认是 `I_UNDERSTAND_LIVE_RISK`

API Key 只授予所需权限，禁止提现并绑定 IP 白名单。现货交易使用读取和现货交易权限；熬鹰跟单额外需要 U 本位合约交易权限。密钥只通过环境变量注入，不能写入仓库、数据库、前端或日志。

运行页的操作顺序是：输入确认短语、解锁实盘、检查 Binance 账户、填写方向和数量、提交市价单。系统先检查实时价格、风控限额和 Kill Switch。请求超时后按客户端订单号查询 Binance，不直接重复下单。`POST /api/orders` 始终拒绝绕过风控的直接下单。

配置了 API Key 且实时行情开启时，API 每 60 秒读取现货余额。某个币种的策略持仓合计大于交易所余额时，风险页显示告警，并拒绝新的买入；卖出和平仓仍可继续。

Testnet 使用 `https://testnet.binance.vision`，只验证执行状态，不用于评估策略收益。

## 熬鹰监控

`/copy` 读取币安公开带单账户「熬鹰资本」，固定组合 ID 为 `5075281354358777856`。页面展示公开收益、规模、风险标签和最近平仓。当前持仓只在带单员开启 `positionShow` 时显示。

`POST /api/copy/aoying` 在持仓公开、实盘解锁且确认短语正确时执行。它按各持仓名义价值比例分配 `quote_amount`，在调用方自己的 U 本位合约账户开仓，并把杠杆设为 1 倍。金额必须大于 0 且不超过 `MAX_ORDER_NOTIONAL`。持仓未公开或当前没有持仓时返回 409，系统不会根据平仓记录推测隐藏仓位。

合约接口地址由 `BINANCE_FUTURES_BASE_URL` 控制，默认是 `https://fapi.binance.com`。

## 安全边界

- 登录接口以外的业务 API 都需要 JWT。
- 控制面不能直接构造交易所订单，实盘请求仍经过解锁检查和风控。
- 单笔名义金额默认不超过 100，单日亏损默认不超过 25。
- 全局停止后拒绝新的实盘订单。
- 常规测试不连接交易所，也不使用真实密钥。

备份、密钥轮换和事故处理见 [docs/operations.md](docs/operations.md)。
