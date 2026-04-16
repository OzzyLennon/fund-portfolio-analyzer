#!/usr/bin/env python3
"""
Portfolio Monitor - 组合健康检查与自动触发
============================================
检查内容：
  1. 持仓基金单日涨跌幅（触发阈值：±3%）
  2. 持仓基金连续N日异常涨跌（触发阈值：连续3天±2%/天）
  3. 市场整体快速下跌检测

用法:
  python3 portfolio_monitor.py --check-triggers
  python3 portfolio_monitor.py --daily-brief
  python3 portfolio_monitor.py --weekly-deep
"""

import sys
import os
import json
import argparse
import warnings
import datetime
warnings.filterwarnings('ignore')

for v in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(v, None)

import akshare as ak
import pandas as pd


PORTFOLIO = [
    {'code': '110020', 'name': '易方达沪深300ETF联接A',  'is_bond': False},
    {'code': '008585', 'name': '华夏人工智能ETF联接A',  'is_bond': False},
    {'code': '023902', 'name': '博道上证科创板综合指数增强C','is_bond': False},
    {'code': '014125', 'name': '华夏中证1000指数增强A',  'is_bond': False},
    {'code': '004200', 'name': '博时富瑞纯债债券A',      'is_bond': True},
    {'code': '217022', 'name': '招商产业债券A',          'is_bond': True},
    {'code': '009033', 'name': '建信上海金ETF联接A',    'is_bond': False},
    {'code': '008009', 'name': '华商高端装备制造股票A', 'is_bond': False},
    {'code': '004237', 'name': '中欧新蓝筹灵活配置混合C','is_bond': False},
    {'code': '004814', 'name': '中欧红利优享灵活配置混合A','is_bond': False},
    {'code': '004815', 'name': '中欧红利优享灵活配置混合C','is_bond': False},
]

# 触发阈值
SINGLE_DAY_THRESHOLD = 3.0      # 单日涨跌超±3%触发
CONSECUTIVE_DAYS = 3            # 连续N天
CONSECUTIVE_THRESHOLD = 2.0     # 每天涨跌超±2%
MARKET_DROP_THRESHOLD = -2.5    # 大盘单日跌超-2.5%


def get_realtime_prices() -> dict:
    """获取所有持仓基金实时数据"""
    try:
        df = ak.fund_open_fund_daily_em()
        prices = {}
        for h in PORTFOLIO:
            row = df[df['基金代码'].astype(str) == h['code']]
            if not row.empty:
                change = float(row.iloc[0].get('日增长率') or 0)
                nav = row.iloc[0].get('单位净值') or row.iloc[0].get('2026-04-16-单位净值') or 0
                prices[h['code']] = {
                    'change': change,
                    'nav': float(nav) if nav else 0,
                    'name': h['name'],
                }
        return prices
    except Exception as e:
        print(f"获取实时价格失败: {e}", file=sys.stderr)
        return {}


def get_fund_history_5d(code: str) -> list:
    """获取近5日日涨跌幅"""
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator='单位净值走势', period='6个月')
        if df is None or df.empty:
            return []
        df['日增长率'] = pd.to_numeric(df['日增长率'], errors='coerce')
        df = df.dropna(subset=['日增长率']).tail(5)
        return df['日增长率'].tolist()
    except Exception:
        return []


def check_triggers(prices: dict) -> dict:
    """检查所有触发条件"""
    alerts = []
    triggered = False

    for code, data in prices.items():
        change = data['change']
        name = data['name']

        # 1. 单日大幅涨跌
        if abs(change) >= SINGLE_DAY_THRESHOLD:
            direction = "暴涨" if change > 0 else "暴跌"
            alerts.append({
                'type': 'single_day',
                'fund': name,
                'code': code,
                'change': change,
                'message': f"🚨 {name}（{code}）{direction} {change:+.2f}%，触发单日大幅波动预警！",
            })
            triggered = True

        # 2. 连续异常涨跌
        history_5d = get_fund_history_5d(code)
        if len(history_5d) >= CONSECUTIVE_DAYS:
            consecutive = all(abs(d) >= CONSECUTIVE_THRESHOLD for d in history_5d[-CONSECUTIVE_DAYS:])
            if consecutive:
                same_direction = all(d * history_5d[-1] > 0 for d in history_5d[-CONSECUTIVE_DAYS:])
                if same_direction:
                    direction = "连续上涨" if history_5d[-1] > 0 else "连续下跌"
                    changes_str = '/'.join([f"{d:+.2f}%" for d in history_5d[-CONSECUTIVE_DAYS:]])
                    alerts.append({
                        'type': 'consecutive',
                        'fund': name,
                        'code': code,
                        'changes': history_5d[-CONSECUTIVE_DAYS:],
                        'message': f"🚨 {name}（{code}）连续{CONSECUTIVE_DAYS}天{history_5d[-1]:+.2f}%趋势（{changes_str}），触发连续异常波动预警！",
                    })
                    triggered = True

    # 3. 大盘健康检查（沪深300）
    if '110020' in prices:
        hs300_change = prices['110020']['change']
        if hs300_change <= -MARKET_DROP_THRESHOLD:
            alerts.append({
                'type': 'market_drop',
                'fund': '沪深300',
                'code': '110020',
                'change': hs300_change,
                'message': f"🌐 沪深300今日下跌 {hs300_change:.2f}%，市场整体承压，建议检查组合风险！",
            })
            triggered = True

    return {
        'triggered': triggered,
        'alerts': alerts,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def generate_daily_brief(prices: dict) -> str:
    """生成每日晨报"""
    lines = []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append(f"# 📰 基金组合每日晨报")
    lines.append(f"**时间：{now}**")
    lines.append("")

    if not prices:
        lines.append("⚠️ 暂时无法获取基金数据，请稍后重试")
        return '\n'.join(lines)

    # 汇总
    total_change = sum(p['change'] for p in prices.values()) / len(prices)
    best = max(prices.items(), key=lambda x: x[1]['change'])
    worst = min(prices.items(), key=lambda x: x[1]['change'])

    lines.append(f"**组合今日涨跌：{total_change:+.2f}%**")
    lines.append(f"**最强：{best[1]['name']} {best[1]['change']:+.2f}%**")
    lines.append(f"**最弱：{worst[1]['name']} {worst[1]['change']:+.2f}%**")
    lines.append("")

    # 明细
    lines.append("| 基金 | 代码 | 今日涨跌 |")
    lines.append("|------|------|---------|")
    for h in PORTFOLIO:
        if h['code'] in prices:
            p = prices[h['code']]
            icon = "🔴" if p['change'] < -1 else ("🟢" if p['change'] > 1 else "⚪")
            lines.append(f"| {icon}{h['name'][:10]} | {h['code']} | {p['change']:+.2f}% |")

    lines.append("")
    lines.append("*注：±3%单日波动或连续3天±2%/天将自动触发深度分析*")

    return '\n'.join(lines)


def run_deep_analysis() -> str:
    """调用深度分析脚本"""
    import subprocess
    script_path = os.path.join(os.path.dirname(__file__), 'portfolio_deep_analyzer.py')
    result = subprocess.run(
        ['python3', script_path, '--holdings', json.dumps(PORTFOLIO)],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, 'HTTP_PROXY': '', 'HTTPS_PROXY': ''}
    )
    return result.stdout if result.returncode == 0 else f"深度分析执行失败: {result.stderr}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-triggers', action='store_true', help='检查触发条件')
    parser.add_argument('--daily-brief', action='store_true', help='生成每日晨报')
    parser.add_argument('--weekly-deep', action='store_true', help='每周深度分析')
    parser.add_argument('--auto-deep', type=str, help='自动触发深度分析（传入告警JSON）')
    args = parser.parse_args()

    if args.check_triggers:
        print("检查触发条件...", file=sys.stderr)
        prices = get_realtime_prices()
        result = check_triggers(prices)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['triggered']:
            print("\n--- 触发深度分析 ---", file=sys.stderr)
            deep_report = run_deep_analysis()
            print(deep_report)

    elif args.daily_brief:
        prices = get_realtime_prices()
        brief = generate_daily_brief(prices)
        print(brief)

    elif args.weekly_deep:
        print("运行每周深度分析...", file=sys.stderr)
        report = run_deep_analysis()
        print(report)

    elif args.auto_deep:
        alert_data = json.loads(args.auto_deep)
        alerts = alert_data.get('alerts', [])
        if alerts:
            print(f"⚠️ 触发事件: {alerts[0]['message']}", file=sys.stderr)
            report = run_deep_analysis()
            print(report)
        else:
            print("无触发事件")

    else:
        # 默认：检查触发
        prices = get_realtime_prices()
        result = check_triggers(prices)
        if result['triggered']:
            print("🚨 触发告警:", file=sys.stderr)
            for a in result['alerts']:
                print(f"  {a['message']}", file=sys.stderr)
        else:
            brief = generate_daily_brief(prices)
            print(brief)


if __name__ == "__main__":
    main()
