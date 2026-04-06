# 日志记录系统文档

## 概述

该项目采用了增强的日志记录机制，可以详细记录交易失败的具体原因，包括堆栈跟踪、请求参数和异常信息。

## 日志输出

### 日志文件位置
- **scheduler.log** - 调度器运行日志（位于项目根目录）
- **logs/** 目录 - 其他模块详细日志（可选，使用 logging_utils 时）

### 日志级别

| 级别 | 用途 | 示例 |
|------|------|------|
| **INFO** | 正常操作日志 | 交易执行成功、信号生成等 |
| **WARNING** | 潜在问题 | API 密钥未设置、位置不同步 |
| **ERROR** | 操作失败 | 交易执行失败、API 请求失败 |

## 交易日志示例

### 交易执行成功

```
2025-04-06 10:30:45 [INFO] [TRADE] user123/AAPL -> BUY x10 @ 150.25
```

### 交易执行失败（包含详细原因）

```
2025-04-06 10:31:15 [ERROR] [TRADE] user123/AAPL failed: Alpaca API error: Insufficient buying power | signal=BUY, quantity=10
Traceback (most recent call last):
  File "src/services/trading_sessions.py", line 120, in trade_for_user
    order = orchestrator.execution_agent.execute_trade(...)
  File "src/agentic_trading.py", line 318, in execute_trade
    result = alpaca_execute_trade(...)
  File "src/broker_alpaca.py", line 88, in submit_market_order
    order = client.submit_order(order_data=order_request)
  File "alpaca/trading/client.py", line 500, in submit_order
    raise InsufficientFundsError("Insufficient buying power")
```

## 日志记录位置及其改进

### 1. 分析会话 (`trading_sessions.py::analyze_for_user`)
- **改进**: 添加了 `exc_info=True` 以记录完整堆栈跟踪
- **日志格式**: `[ANALYZE] {user_id}/{symbol} failed: {exception}` + traceback

**示例**:
```
2025-04-06 10:25:00 [ERROR] [ANALYZE] user123/TSLA failed: LLM unavailable
Traceback (most recent call last):
  ...
```

### 2. 交易会话 (`trading_sessions.py::trade_for_user`)
- **改进**: 
  - 添加了 `exc_info=True` 记录堆栈跟踪
  - 包含交易上下文：`signal`, `quantity`
- **日志格式**: `[TRADE] {user_id}/{symbol} failed: {exception} | signal={signal}, quantity={qty}` + traceback

**示例**:
```
2025-04-06 10:30:15 [ERROR] [TRADE] user123/AAPL failed: Connection timeout | signal=BUY, quantity=10
Traceback (most recent call last):
  ...
```

### 3. 平仓会话 (`trading_sessions.py::close_for_user`)
- **改进**: 
  - 添加了 `exc_info=True` 记录堆栈跟踪
  - 包含平仓上下文：`side`, `quantity`
- **日志格式**: `[CLOSE] {user_id}/{symbol} failed: {exception} | side={side}, quantity={qty}` + traceback

**示例**:
```
2025-04-06 16:00:30 [ERROR] [CLOSE] user123/MSFT failed: Order rejected | side=SELL, quantity=5
Traceback (most recent call last):
  ...
```

### 4. Broker 集成 (`broker_alpaca.py`)

#### submit_market_order
- **改进**: 添加异常处理和日志
- **成功日志**: `[MARKET] {symbol} {side} x{qty} -> order_id={order_id}, status={status}`
- **失败日志**: `[MARKET] {symbol} {side} x{qty} failed: {exception}` + traceback

#### submit_limit_order
- **改进**: 添加异常处理和日志
- **成功日志**: `[LIMIT] {symbol} {side} x{qty} @ {limit_price} -> order_id={order_id}`
- **失败日志**: `[LIMIT] {symbol} {side} x{qty} @ {limit_price} failed: {exception}` + traceback

#### submit_stop_order
- **改进**: 添加异常处理和日志
- **成功日志**: `[STOP] {symbol} {side} x{qty} @ {stop_price} -> order_id={order_id}`
- **失败日志**: `[STOP] {symbol} {side} x{qty} @ {stop_price} failed: {exception}` + traceback

#### execute_trade
- **改进**: 
  - 添加异常处理和日志
  - 包含完整交易参数：`strategy`, `stop_loss`, `take_profit`
- **成功日志**: `[EXECUTE] {symbol} {side} x{qty} ({strategy}) completed with {n} order(s)`
- **失败日志**: `[EXECUTE] {symbol} {side} x{qty} ({strategy}) failed: {exception} | stop_loss={sl}, take_profit={tp}` + traceback

#### reconcile_positions
- **改进**: 
  - 添加异常处理和日志
  - 记录同步状态
- **成功日志**: `[RECONCILE] {user_id} -- {n} positions in sync`
- **不同步日志**: `[RECONCILE] {user_id} -- {n} position(s) out of sync: {diffs}`
- **失败日志**: `[RECONCILE] {user_id} failed: {exception}` + traceback

### 5. 执行代理 (`agentic_trading.py::ExecutionAgent`)
- **改进**: 
  - 添加异常处理和日志
  - 成功和失败时都记录详细信息
- **日志格式**:
  - 成功: `[EXEC] {symbol} {side} x{qty} @ {price} ({strategy}) -> order_id={order_id}`
  - 失败: `[EXEC] {symbol} {side} x{qty} @ {price} ({strategy}) failed: {exception}` + traceback

## 常见错误和日志

### 1. 资金不足错误
```
[ERROR] [MARKET] AAPL BUY x100 failed: Alpaca API error: Insufficient buying power
```
**原因**: 账户现金不足以购买请求的数量
**解决**: 检查账户余额或降低交易量

### 2. API 凭证错误
```
[ERROR] [EXEC] MSFT SELL x50 failed: Alpaca API error: Invalid credentials
```
**原因**: API 密钥或密钥无效或过期
**解决**: 验证 .env 文件中的凭证

### 3. 网络连接错误
```
[ERROR] [MARKET] GOOGL BUY x10 failed: Connection timeout
```
**原因**: 网络连接问题或 Alpaca 服务不可用
**解决**: 检查网络连接，稍后重试

### 4. LLM 解析失败
```
[WARNING] [TECH] TSLA LLM parsing failed: Invalid JSON response, using fallback analysis
```
**原因**: LLM 返回的响应无法解析
**处理**: 系统自动使用量化分析作为备选方案

### 5. 位置不同步
```
[WARNING] [RECONCILE] user123/AAPL -- broker=100 db=95
```
**原因**: Broker 中的持仓与本地数据库不同步
**解决**: 检查最近的交易，确保 DB 与 Broker 一致

## 使用日志工具模块

可以使用新创建的 `logging_utils.py` 模块来设置和使用结构化日志：

```python
from logging_utils import setup_logging, TradeLogger

# 设置模块日志
logger = setup_logging(__name__)
trade_logger = TradeLogger(logger)

# 记录交易执行
trade_logger.log_trade_execution(
    user_id="user123",
    symbol="AAPL",
    side="BUY",
    quantity=10,
    price=150.25,
    order_id="ord_12345"
)

# 记录交易失败
trade_logger.log_trade_failure(
    user_id="user123",
    symbol="AAPL",
    side="BUY",
    quantity=10,
    reason="Insufficient buying power",
    error=e
)

# 记录信号
trade_logger.log_signal_generated(
    user_id="user123",
    symbol="AAPL",
    signal="BUY",
    confidence=0.85,
    technical_score=0.8,
    sentiment_score=0.7
)
```

## 查看日志

### 实时查看
```bash
# 查看调度器日志
tail -f scheduler.log

# 查看全部日志
tail -f logs/*.log
```

### 搜索特定用户的日志
```bash
grep "user123" scheduler.log

# 搜索特定符号的日志
grep "AAPL" scheduler.log

# 搜索所有错误日志
grep "ERROR" scheduler.log
```

### 搜索特定时间的日志
```bash
# 查看 10:30 之后的日志
grep "10:3[0-9]" scheduler.log
```

## 日志中包含的关键信息

交易失败时，日志记录包括：

1. **用户标识**: `{user_id}` - 识别是哪个用户的交易失败
2. **符号**: `{symbol}` - 交易的股票符号
3. **交易详情**: `side`, `quantity`, `price` - 交易参数
4. **异常信息**: 具体的错误消息
5. **堆栈跟踪**: 完整的调用栈，显示错误发生的位置
6. **额外上下文**: `stop_loss`, `take_profit`, `strategy` 等参数

这使得调试和监控交易系统变得容易得多。

## 总结

改进的日志系统现在可以：
✅ 记录交易失败的具体原因
✅ 显示完整的堆栈跟踪便于定位问题
✅ 包含请求的上下文信息
✅ 区分不同类型的错误（API 错误、网络错误、业务逻辑错误等）
✅ 支持结构化日志记录
✅ 自动日志轮转以管理磁盘空间
