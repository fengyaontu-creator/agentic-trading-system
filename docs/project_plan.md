# Agentic AI for Trading — 项目方案 & 分工

## 一、项目全景

在老师模板（4-agent框架）基础上，做以下**六大扩展**，让项目从"填空题"变成有实质深度的完整系统。

---

## 二、系统架构

```
                    ┌─────────────────┐
                    │   Orchestrator   │
                    │  (统筹 + 调度)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Data Layer  │   │  Analysis    │   │  Execution   │
│              │   │  Layer       │   │  Layer       │
│ • yfinance   │   │ • Technical  │   │ • Alpaca API │
│ • NewsAPI    │   │   Agent      │   │ • Order Mgmt │
│ • Reddit/    │   │ • Sentiment  │   │ • Paper      │
│   FinViz     │   │   Agent      │   │   Trading    │
└──────┬───────┘   │ • Risk Agent │   └──────┬───────┘
       │           └──────┬───────┘          │
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────────────────────────────────────────┐
│              Backtesting & Evaluation            │
│  • 历史回测  • Sharpe/Sortino  • 最大回撤  • 收益曲线  │
└─────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│              Dashboard & Reporting               │
│  • 交易日志  • 可视化面板  • 结果导出              │
└─────────────────────────────────────────────────┘
```

---

## 三、五人分工

### 👤 Person A（Nora）— 架构统筹 + Technical Analysis 改造
**工作量：10-12 小时**

**职责：**
1. **统筹整合** — 定义模块接口，确保五人代码能合并运行
2. **改造 `fetch_market_data`** — 用 yfinance 替换随机数据
   - `yf.download(symbol, period="3mo", interval="1h")` 获取真实 OHLCV
   - 保留模板里的技术指标计算逻辑（SMA/EMA/RSI/MACD/BB）
3. **加入 ML 增强分析**（加分项）
   - 将之前 lab 的 RSI pair trading / MACD 策略逻辑封装为函数
   - 让 Technical Agent 除了 LLM 判断外，还参考量化信号
   - 例：RSI < 30 且 MACD 金叉 → 额外 confidence boost
4. **代码整合与测试** — 最后把所有人的模块合并，跑通端到端

**具体改动：**
```python
# 改前（模板）：随机数据
returns = np.random.randn(period) * 0.02
prices = base_price * np.exp(np.cumsum(returns))

# 改后：真实数据
import yfinance as yf
ticker = yf.Ticker(symbol)
df = ticker.history(period="3mo", interval="1h")
# 然后保留原有的技术指标计算...
```

**交付物：**
- `data_tools.py` — yfinance 数据获取 + 技术指标计算
- `ml_signals.py` — ML/量化策略增强信号（可选）
- 最终整合版 `agentic_trading_final.py`

---

### 👤 Person B — Sentiment Analysis 改造（多源情绪融合）
**工作量：8-10 小时**

**职责：**
1. **接入 NewsAPI**（免费 tier，developer.newsapi.org）
   - 按 symbol 搜索最近 7 天新闻标题
   - 用 LLM 对标题做情绪打分（-1 到 +1）
2. **接入 FinViz 或 Reddit 情绪**（二选一，作为第二数据源）
   - FinViz：爬取 analyst ratings / news headlines
   - Reddit：用 PRAW 库拉取 r/wallstreetbets 或 r/stocks 相关帖子
3. **多源融合逻辑**
   - 加权平均：NewsAPI 权重 0.6 + FinViz/Reddit 权重 0.4
   - 置信度调整：数据源越多、信号越一致，confidence 越高

**具体改动：**
```python
# 改前（模板）：随机情绪
sentiment_score = np.random.uniform(-1, 1)

# 改后：真实新闻 + LLM 情绪判断
from newsapi import NewsApiClient
newsapi = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
articles = newsapi.get_everything(q=symbol, language='en', sort_by='publishedAt')
headlines = [a['title'] for a in articles['articles'][:10]]
# 然后用 LLM 对 headlines 做情绪分析...
```

**交付物：**
- `sentiment_tools.py` — 多源情绪数据获取 + 融合逻辑
- 改造后的 `SentimentAnalysisAgent` 类

---

### 👤 Person C — Alpaca API 接入 + 订单管理
**工作量：8-10 小时**

**职责：**
1. **注册 Alpaca paper trading 账户**，获取 API key
2. **改造 `ExecutionAgent.execute_trade`**
   - 用 `alpaca-trade-api` SDK 替换模拟下单
   - 支持 market order / limit order / stop order
3. **增加订单管理功能**
   - 查询账户余额、持仓
   - 查询订单状态（filled / partial / canceled）
   - 实现止损/止盈自动挂单
4. **MCP 集成**（加分项）
   - 参考老师给的 Alpaca MCP 链接

**具体改动：**
```python
# 改前（模板）：模拟下单
slippage = np.random.uniform(-0.001, 0.001)
execution_price = price * (1 + slippage)
order = {'order_id': f"ORD_{...}", 'status': 'FILLED'}

# 改后：Alpaca 真实下单
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

client = TradingClient(api_key, secret_key, paper=True)
order_data = MarketOrderRequest(
    symbol=symbol,
    qty=quantity,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY
)
order = client.submit_order(order_data)
```

**交付物：**
- `broker_alpaca.py` — Alpaca 连接 + 下单 + 查询封装
- 改造后的 `ExecutionAgent` 类
- `.env.example` — 环境变量模板

---

### 👤 Person D — 回测框架 + 风控增强
**工作量：8-10 小时**

**职责：**
1. **历史回测框架**
   - 用 yfinance 拉 6 个月 ~ 1 年历史数据
   - 循环调用 agent pipeline，模拟多天交易
   - 记录每笔交易的 entry/exit/PnL
2. **绩效指标计算**
   - 累计收益曲线
   - Sharpe Ratio / Sortino Ratio
   - 最大回撤（Max Drawdown）
   - 胜率（Win Rate）
   - 盈亏比（Profit Factor）
3. **风控增强**
   - 给 RiskManagementAgent 加入真实的 VaR 计算
   - 基于历史波动率的动态止损
   - 最大持仓集中度限制

**交付物：**
- `backtester.py` — 回测引擎
- `risk_enhanced.py` — 增强版风控逻辑
- 回测结果数据（CSV + 图表）

---

### 👤 Person E — 可视化 Dashboard + PPT + Presentation
**工作量：8-10 小时**

**职责：**
1. **交易结果可视化**（用 matplotlib / plotly）
   - 价格走势 + 买卖点标注
   - 累计收益曲线
   - 持仓分布饼图
   - Agent 决策流程图
2. **PPT 制作**
   - 项目背景 & 动机
   - 系统架构图
   - 各 Agent 功能说明
   - 演示截图 / 运行结果
   - 回测结果分析
   - 总结 & 未来改进
3. **Presentation 准备**
   - 视频录制或现场演示的脚本
   - 每人 2-3 分钟的讲解分工

**交付物：**
- `dashboard.py` — 可视化脚本
- `Project6_Presentation.pptx` — 演示 PPT
- 演示视频（如需要）

---

## 四、时间线

| 阶段 | 时间 | 内容 |
|------|------|------|
| Week 1 | Day 1-2 | A 定义接口规范，发给 B/C/D；各自开始独立开发 |
| Week 1 | Day 3-5 | B 完成 Sentiment，C 完成 Alpaca，D 开始回测框架 |
| Week 2 | Day 1-2 | A 整合 B/C 代码，跑通端到端 pipeline |
| Week 2 | Day 3-4 | D 跑回测 + 生成结果，E 做可视化 + PPT |
| Week 2 | Day 5 | 全组 review，准备 presentation |

---

## 五、技术栈

| 组件 | 工具 |
|------|------|
| LLM | Claude (Anthropic API) via LangChain |
| 数据 | yfinance, NewsAPI, FinViz/Reddit |
| 券商 | Alpaca (paper trading) |
| 框架 | LangChain, Pydantic |
| 回测 | 自建（基于 pandas） |
| 可视化 | matplotlib / plotly |
| 环境管理 | dotenv, requirements.txt |

---

## 六、需要的 API Keys（.env 文件）

```
ANTHROPIC_API_KEY=sk-ant-...
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
NEWS_API_KEY=...
```

---

## 七、评分亮点

老师模板只有 4 个 agent + 随机数据 + 模拟下单。你们的增强点：

1. ✅ 真实市场数据（yfinance）
2. ✅ 真实新闻情绪（多源融合）
3. ✅ 真实券商下单（Alpaca paper trading）
4. ✅ ML/量化策略增强（RSI/MACD 信号）
5. ✅ 完整回测框架 + 绩效指标
6. ✅ 风控增强（VaR、动态止损）
7. ✅ 可视化 Dashboard
8. ✅ MCP 集成（加分项）
