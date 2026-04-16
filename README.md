# A-Share Fund Portfolio Analyzer

A professional A-share fund portfolio analysis toolkit for Chinese investors.

## 功能特性

- 📊 **持仓分析**：支持截图 OCR 识别或直接 API 模式输入基金代码
- 📈 **历史净值**：AkShare 数据源，支持 1月/3月/6月/1年/2年收益分析
- 📉 **风险指标**：年化波动率、最大回撤、夏普比率、卡玛比率
- 🔍 **趋势信号**：基于均线交叉判断短期趋势（上升/下降/震荡）
- 🏭 **持仓穿透**：基金前10大重仓股/行业配置（AkShare数据）
- 📰 **消息面**：MiniMax 搜索实时新闻
- 🌍 **国际局势**：美联储/中美关系/地缘对A股影响评估
- 🎯 **综合评分**：0-100分持有建议（强烈建议持有/建议持有/建议减仓/建议清仓）
- 🔄 **调仓建议**：卖出标的（含替代方案）+ 加仓板块推荐
- 👀 **关注板块**：暂未持仓但值得关注的板块及标的
- ⏰ **自动监测**：支持每日晨报、每周深度、事件触发监控

## 快速开始

### 环境要求

- Python 3.8+
- 依赖：`pip install akshare pandas`

### 分析你的持仓

```bash
# 基础分析（截图OCR）
python3 portfolio_analyzer.py --screenshot /path/to/screenshot.png

# API模式（直接输入基金代码）
python3 portfolio_analyzer.py --codes 110020,008585,009033

# 深度分析（含持仓/行业/消息/评分）
python3 portfolio_deep_analyzer.py --codes 110020,008585,023902

# 完整持仓（含调仓建议）
python3 portfolio_deep_analyzer.py --holdings '[{"code":"110020","name":"易方达沪深300ETF联接A","is_bond":false}]'

# 每日晨报
python3 portfolio_monitor.py --daily-brief

# 触发检测（单日±3%或连续3天±2%自动深度分析）
python3 portfolio_monitor.py --check-triggers
```

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `portfolio_analyzer.py` | 基础持仓分析（净值+风险指标+趋势信号） |
| `portfolio_deep_analyzer.py` | 深度分析（持仓+行业+消息面+综合评分+调仓建议） |
| `portfolio_monitor.py` | 自动监测（触发检测+晨报生成+定时任务） |

## 持仓格式

```json
[
  {"code": "110020", "name": "易方达沪深300ETF联接A", "is_bond": false},
  {"code": "008585", "name": "华夏人工智能ETF联接A", "is_bond": false},
  {"code": "004200", "name": "博时富瑞纯债债券A", "is_bond": true}
]
```

## 评分体系

| 评分 | 建议 |
|------|------|
| 🟢 70+ | 强烈建议持有 |
| 🟡 55-69 | 建议持有 |
| 🟡 40-54 | 建议减仓 |
| 🔴 <40 | 建议清仓 |

## 数据来源

- 基金净值/持仓：[AkShare](https://github.com/akfamily/akshare) （东方财富）
- 消息面：[MiniMax](https://www.minimaxi.com/) 搜索API
- 实时行情：[AkShare](https://github.com/akfamily/akshare) 基金日频数据

## 免责声明

本工具仅供参考，不构成投资建议。基金投资有风险，入市需谨慎。

---

Star ⭐ 欢迎改进！
