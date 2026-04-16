---
name: fund-portfolio-analyzer
description: A股基金组合深度分析工具。输入持仓数据（截图OCR或JSON），自动计算资产配置、诊断组合问题、输出调仓建议。支持 AkShare 在线数据（网络可用时）和离线OCR数据两种模式。
version: 1.0.0
commands:
  - portfolio_analyzer.py
inputs:
  - OCR截图文本
  - 持仓JSON数据
  - 手动输入基金+金额
outputs:
  - 资产配置饼图分析
  - 问题诊断报告
  - 调仓优先级建议
  - 分类仓位评价
---

# 基金组合深度分析 skill

## 使用方式

### 方式1：截图 + 我来 OCR
直接发持仓截图给我，我自动识别并分析

### 方式2：直接告诉我
告诉我基金名称和金额，例如：
> 易方达沪深300 ETF联接A 12万，华夏人工智能 ETF 6.3万...

### 方式3：JSON 数据
```bash
python3 portfolio_analyzer.py --holdings '[{"code":"110020","name":"易方达沪深300","amount":120476}]'
```

### 方式4：测试模式
```bash
python3 portfolio_analyzer.py --test
```

## 分析维度

- **资产配置全景** — A股权重、黄金、债券、现金占比
- **问题诊断** — 重复持仓、集中度过高、防御不足
- **调仓建议** — 优先级排序的具体操作建议
- **分类评价** — 每类资产的仓位健康度

## 数据来源

- 在线模式：AkShare → 东方财富/天天基金（需要网络通）
- 离线模式：OCR 截图数据（当前主要模式）

## 适用场景

- 定期持仓复盘
- 调仓前后对比
- 新增持仓预分析
