# 个人加密货币量化平台

面向 Binance 现货的个人研究、回测、模拟盘和实盘控制台。默认模式是 `paper`，实盘开关默认关闭。

## 本地开发

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest
python -m app.store.migrate
python -m uvicorn app.main:app --reload

cd ..\frontend
npm install
npm run lint
npm run build
npm run dev
```

后端测试使用 SQLite 和伪造的交易所传输层，不会访问 Binance，也不会发送真实订单。当前机器未安装 Docker 时，仍可按上面的命令运行；Docker Compose 负责可复现的 PostgreSQL、Redis、API、worker、runtime 和前端部署。

## 研究流程

1. 导入闭合 K 线并生成数据集摘要。重复、乱序、缺口或未闭合 K 线会使数据集不可交易。
2. 对冻结的数据集运行 SMA 交叉示例策略。同一运行清单必须得到相同的成交指纹。
3. 查看回测假设、前视偏差检查和 walk-forward 结果。
4. 先启动模拟盘。只有连接器就绪且账户已对账时，运行时才会接受订单。

## 安全边界

- API 控制面不能直接下单，交易命令进入独立 runtime。
- 网络超时进入 `UNKNOWN`，必须先按客户端订单 ID 查询，禁止盲目重试。
- 实盘同时需要 `LIVE_BUILD_ENABLED`、`LIVE_TRADING_ENABLED` 和确认短语。
- API Key 只通过环境变量注入，权限应限制为交易、禁止提现并绑定 IP 白名单。

操作、备份和事故处理见 [docs/operations.md](docs/operations.md)。
