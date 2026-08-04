---
name: stock-analysis
description: TradingAgents 股票分析：装环境、跑多智能体个股深度分析（美股 + A 股新闻/情绪），含配置、运行与排障。
---

# 股票分析（TradingAgents 多智能体）

在 TradingAgents 仓库中安装环境并运行个股深度分析：LLM 多智能体流水线（技术面/基本面/新闻/情绪 4 分析师 → 多空辩论 → 交易员 → 风控 → 组合经理），输出中文报告与决策（Underweight / Hold / Overweight）。

支持两类标的：
- **美股**：yfinance 数据源（行情/基本面/新闻），情绪用 StockTwits/Reddit
- **A 股**：AkShare + 东方财富数据源（本仓库已内置 `akshare_news.py` 并默认启用），新闻/情绪齐全

## 前置条件

- 已 clone 本仓库（内含 `scripts/run_stock.py`、`scripts/quick_ta.py`、`tradingagents/dataflows/akshare_news.py`）
- 本机有 conda（或 Python 3.10+）
- 至少一个 LLM API key（推荐 DeepSeek `DEEPSEEK_API_KEY`，便宜且对 A 股公司理解好、中文输出自然）

## 安装步骤（在仓库根目录执行）

```bash
# 1. 环境
conda create -n tradingagents python=3.12 -y
conda activate tradingagents

# 2. 依赖。注意 cryptography<49：49+ 不再提供 Intel Mac wheel，
#    源码编译需要新版 Rust，容易失败；<49 有预编译 wheel。
python -m pip install "cryptography<49" .
python -m pip install akshare        # A 股新闻/情绪数据源（可选但推荐）

# 3. API key
cp .env.example .env
# 编辑 .env，至少填 DEEPSEEK_API_KEY=sk-xxx（或 OPENAI/GOOGLE/ANTHROPIC 任选）

# 4.（仅 Yahoo 数据被限流/403 时需要）走代理：
export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890
```

> 若 agent 运行在受限沙箱（无法写 conda 环境），把上面的安装命令交给用户在其终端执行；运行分析同理。

## 运行分析

```bash
# 数据流自检（不调 LLM，快速验证行情+技术指标可拉取）
python scripts/quick_ta.py [YYYY-MM-DD]

# 单股非交互分析（推荐）：
#   python scripts/run_stock.py <TICKER> <日期> <分析师,列表>
python scripts/run_stock.py 600036.SS 2026-08-04 market,fundamentals,news,social
python scripts/run_stock.py AAPL 2026-08-03 market

# 交互式 CLI（弹菜单选择）
tradingagents analyze
```

> **源码 vs 安装版**：`python scripts/run_stock.py` / `python scripts/quick_ta.py` 已内置仓库根到 `sys.path`，始终使用仓库源码（含 AkShare 改造）。`tradingagents` 命令来自 pip 安装副本——若 clone 后改了仓库代码（或要启用 akshare），交互式 CLI 请改用 `python -m cli.main`（从仓库根运行，命中源码），或先 `pip install .` 重装。

## 关键约定

- **A 股 ticker 必须带交易所后缀**：沪 `600036.SS`、深 `000001.SZ`、北 `8xxxxx.BJ`；裸 6 位数字也能识别，但带后缀最稳。美股用 `AAPL` 等。
- **分析日期**：用最近一个交易日。A 股 `2026-08-04` 这种当天收盘后即可；美股注意美股交易日历。
- **分析师**：`market`(技术面) `fundamentals`(基本面) `news`(新闻) `social`(情绪)。
  - A 股推荐全开：news/social 已由 AkShare/东财数据支撑。
  - 美股若只想看技术面可只开 `market`。
- 默认输出语言为中文（config `output_language=Chinese`，LLM provider 默认 deepseek；可通过 `TRADINGAGENTS_LLM_PROVIDER` 等环境变量覆盖）。
- 运行时产物写入 `.ta_run/`（已 gitignore）：`results/<TICKER>_<DATE>_result.json` 含 `market_report` / `fundamentals_report` / `final_trade_decision`；决策键在 `final_trade_decision` 末尾 `FINAL TRANSACTION PROPOSAL: BUY/HOLD/SELL` 与最终 `Underweight/Hold/Overweight`。

## 排障

| 症状 | 原因 | 处理 |
|---|---|---|
| `pip: /usr/bin/python: bad interpreter` | 系统 pip 脚本指向不存在的 Python | 用 `python -m pip ...` 代替 `pip ...` |
| cryptography 构建报 `lock file version 4` / Cargo 错误 | cryptography≥49 无 Intel Mac wheel，走源码编译且 Rust 太老 | 先 `python -m pip install "cryptography<49"` 再装项目 |
| Yahoo `403 sad panda` / `YFRateLimitError` | 出口 IP 被 Yahoo 反爬/限流 | export 代理（见上）；或等待限流窗口（429 按小时计），勿高频重试 |
| A 股新闻为空 / 情绪不可用 | akshare 未安装或东财接口被限 | `pip install akshare`；千股千评首次拉取约 5 秒（有 1 小时缓存） |
| `NoMarketDataError: no rows` | 日期非交易日或 ticker 格式错 | 换最近交易日；确认后缀 `.SS/.SZ` |

## 结果解读要点

- 决策是 LLM 综合判断，供参考，不构成投资建议。
- 关注 `final_trade_decision` 里给出的关键价位（支撑/阻力/止损）与触发条件，比单看 BUY/HOLD/SELL 更有信息量。
- A 股基本面注意 Yahoo 对中小盘覆盖可能不全（大盘蓝筹如招行/茅台完整）；不良率/拨备覆盖率等银行特有指标 Yahoo 不披露，报告中会标注缺口。
