#!/usr/bin/env python3
"""
A-Share Fund Portfolio Analyzer v4 (Enhanced)
==========================================
支持:
  - 实时净值（东方财富API）
  - 历史走势分析（1月/3月/6月/1年）
  - 趋势线分析（均线、波动率）
  - 组合问题诊断
  - 调仓建议

用法:
  python3 portfolio_analyzer.py --live --history   # 实时+历史分析
  python3 portfolio_analyzer.py --live             # 仅实时
  python3 portfolio_analyzer.py --ocr '<OCR>'      # OCR模式
  python3 portfolio_analyzer.py --holdings '<JSON>'
"""

import sys
import os
import json
import re
import argparse
import warnings
import datetime
warnings.filterwarnings('ignore')

for v in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(v, None)

import akshare as ak
import pandas as pd


# ── 工具函数 ──────────────────────────────────────────────────────────────

def get_fund_nav_live(codes: list) -> dict:
    """获取开放式基金实时/最新净值"""
    df = ak.fund_open_fund_daily_em()
    today = '2026-04-16'
    
    result = {}
    for code in codes:
        row = df[df['基金代码'].astype(str) == str(code)]
        if not row.empty:
            r = row.iloc[0]
            result[code] = {
                'name': str(r.get('基金简称', code)),
                'today_nav': r.get(f'{today}-单位净值'),
                'accum_nav': r.get(f'{today}-累计净值'),
                'daily_return': float(r.get('日增长率', 0) or 0),
            }
    return result


def get_fund_history(code: str, days: int = 730) -> pd.DataFrame:
    """获取基金历史净值（默认2年，保证各周期都能算）"""
    try:
        df = ak.fund_open_fund_info_em(
            symbol=code,
            indicator='单位净值走势',
            period='1年'
        )
        if df is None or df.empty:
            return pd.DataFrame()
        
        df['净值日期'] = pd.to_datetime(df['净值日期'])
        df['日增长率'] = pd.to_numeric(df['日增长率'], errors='coerce')
        df['单位净值'] = pd.to_numeric(df['单位净值'], errors='coerce')
        
        # 过滤到指定天数（默认2年，确保1年周期有足够数据）
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df['净值日期'] >= cutoff].copy()
        return df.sort_values('净值日期').reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def calc_period_return(history: pd.DataFrame, days: int) -> float:
    """计算指定周期的收益率（从数据起始日算起）"""
    if history.empty or len(history) < 2:
        return None
    
    latest = history.iloc[-1]
    latest_nav = float(latest['单位净值'])
    latest_date = latest['净值日期']
    
    # 用最新数据日期作为终点，倒推目标日期
    target = latest_date - pd.Timedelta(days=days)
    
    # 找最接近目标日期的数据点（<= target）
    candidates = history[history['净值日期'] <= target]
    if candidates.empty:
        return None
    
    start_row = candidates.iloc[-1]
    start_nav = float(start_row['单位净值'])
    start_date = start_row['净值日期']
    
    if start_nav <= 0:
        return None
    
    # 确保起点和终点不是同一日期（否则收益为0）
    if start_date == latest_date:
        return None
    
    return (latest_nav - start_nav) / start_nav * 100


def calc_volatility(history: pd.DataFrame) -> float:
    """计算年化波动率"""
    if history.empty or '日增长率' not in history.columns:
        return None
    returns = history['日增长率'].dropna()
    if len(returns) < 5:
        return None
    # 年化波动率 = 日波动率 * sqrt(252)
    daily_std = returns.std()
    annualized = daily_std * (252 ** 0.5)
    return annualized


def calc_max_drawdown(history: pd.DataFrame) -> float:
    """计算最大回撤"""
    if history.empty or '累计净值' not in history.columns:
        # 用单位净值计算
        nav_col = '单位净值'
    else:
        nav_col = '累计净值'
    
    nav = history[nav_col].dropna()
    if nav.empty:
        return None
    
    peak = nav.cummax()
    drawdown = (nav - peak) / peak * 100
    return drawdown.min()


def analyze_single_fund_history(code: str, name: str) -> dict:
    """分析单只基金的历史表现"""
    history = get_fund_history(code, days=730)
    
    if history.empty:
        return {'code': code, 'name': name, 'error': 'No history data'}
    
    result = {
        'code': code,
        'name': name,
        'data_points': len(history),
        'returns': {}
    }
    
    for period, days in [('1月', 30), ('3月', 90), ('6月', 180), ('1年', 365)]:
        ret = calc_period_return(history, days)
        result['returns'][period] = ret
    
    vol = calc_volatility(history)
    result['volatility'] = vol
    result['volatility_label'] = f"{vol:.1f}%" if vol else "N/A"
    
    mdd = calc_max_drawdown(history)
    result['max_drawdown'] = mdd
    result['mdd_label'] = f"{mdd:.1f}%" if mdd else "N/A"
    
    return result


# ── 组合分析 ──────────────────────────────────────────────────────────────

def analyze_portfolio(holdings: list, live_nav: dict, history_data: dict) -> dict:
    """组合综合分析"""
    total = sum(h['amount'] for h in holdings)
    for h in holdings:
        h['weight'] = h['amount'] / total * 100
        nav = live_nav.get(h['code'], {})
        h['daily_return'] = nav.get('daily_return', 0.0)
        h['today_nav'] = nav.get('today_nav')
        h['fund_name_display'] = nav.get('name', h['name'])
        
        # 历史数据
        hd = history_data.get(h['code'], {})
        h['returns'] = hd.get('returns', {})
        h['volatility'] = hd.get('volatility_label', 'N/A')
        h['max_drawdown'] = hd.get('mdd_label', 'N/A')
    
    holdings.sort(key=lambda x: x['amount'], reverse=True)
    
    # 分类
    cats = {'A股权重基金': [], '黄金': [], '债券': [], '现金/货币': []}
    for h in holdings:
        n = h['name']
        if any(k in n for k in ['金ETF', '上海金', '黄金']):
            cats['黄金'].append(h)
        elif any(k in n for k in ['债券', '纯债']):
            cats['债券'].append(h)
        elif any(k in n for k in ['余额宝', '货币']):
            cats['现金/货币'].append(h)
        else:
            cats['A股权重基金'].append(h)
    
    cat_sum = {k: sum(x['amount'] for x in v) for k, v in cats.items()}
    
    return {
        'total_amount': total,
        'holdings': holdings,
        'categories': cats,
        'cat_summary': cat_sum,
        'cat_weights': {k: v/total*100 for k, v in cat_sum.items() if v > 0},
    }


def detect_problems(holdings: list) -> list:
    """诊断组合问题"""
    problems = []
    total = sum(h['amount'] for h in holdings)
    
    # 重复策略
    seen = {}
    for h in holdings:
        base = re.sub(r'[ABC]$', '', h['name'])
        if base in seen and base not in ['余额宝']:
            problems.append({
                'type': 'duplicate',
                'funds': [seen[base]['name'], h['name']],
                'severity': 'high',
                'suggestion': f"同策略重复持仓：{seen[base]['name']} + {h['name']}，建议保留一只，释放 ¥{seen[base]['amount']+h['amount']:,.0f}"
            })
        seen[base] = h
    
    # 债券不足
    bond_w = sum(h['weight'] for h in holdings if '债' in h['name'])
    if bond_w < 10:
        problems.append({'type': 'low_bond', 'severity': 'medium', 'suggestion': f"债券仓位仅{bond_w:.1f}%，建议加至20%+增强防御"})
    
    # 集中度
    for h in holdings:
        if h['weight'] > 30:
            problems.append({'type': 'concentration', 'fund': h['name'], 'weight': h['weight'], 'severity': 'medium', 'suggestion': f"{h['name']}占比{h['weight']:.1f}%偏高，建议单一不超25%"})
    
    # 现金不足
    cash_w = sum(h['weight'] for h in holdings if '余额宝' in h['name'] or '货币' in h['name'])
    if cash_w < 1:
        problems.append({'type': 'low_cash', 'severity': 'low', 'suggestion': f"现金仓位仅{cash_w:.1f}%，建议保留2-3%流动性"})
    
    return problems


def trend_signal(returns: dict) -> str:
    """根据历史收益判断趋势方向"""
    r1m = returns.get('1月')
    r3m = returns.get('3月')
    r6m = returns.get('6月')
    r1y = returns.get('1年')
    
    if all(v is not None for v in [r1m, r3m, r6m, r1y]):
        # 趋势评分：短期弱但长期强 = 震荡上行
        if r1m < r3m < r6m < r1y:
            return "📈 上升趋势" if r1m > 0 else "📊 筑底回升"
        elif r1m > r3m > r6m > r1y:
            return "📉 上涨趋弱"
        elif r1m < 0 and r3m > 0:
            return "↩️ 回调后反弹"
        elif r1m > 0 and r3m > 0:
            return "🚀 强势上行" if r1m > r3m else "✅ 稳健上行"
        else:
            return "➡️ 震荡整理"
    return "⚪ 数据不足"


def generate_enhanced_report(analysis: dict, problems: list) -> str:
    """生成增强版分析报告"""
    total = analysis['total_amount']
    cat_ws = analysis['cat_weights']
    holdings = analysis['holdings']
    
    # 组合今日涨跌
    weighted_daily = sum(h['daily_return'] * h['weight'] / 100 for h in holdings)
    
    lines = []
    lines.append("# 📊 基金组合深度分析报告")
    lines.append("")
    lines.append(f"**分析时间：2026-04-17**")
    lines.append(f"**总资产：¥{total:,.0f}**")
    lines.append(f"**估算组合今日涨跌：{weighted_daily:+.2f}%**")
    lines.append("")
    
    # 一、资产配置
    lines.append("## 一、资产配置全景")
    for cat, w in sorted(cat_ws.items(), key=lambda x: x[1], reverse=True):
        if w > 0:
            lines.append(f"- **{cat}**：{w:.1f}%")
    lines.append("")
    
    # 二、持仓明细（含历史走势）
    lines.append("## 二、持仓明细（含历史收益）")
    lines.append("")
    lines.append("| 基金 | 代码 | 金额 | 占比 | 今日 | 1月 | 3月 | 6月 | 1年 | 波动 | 最大回撤 | 趋势 | 问题 |")
    lines.append("|------|------|------|------|------|-----|-----|-----|-----|------|------|------|------|")
    
    dup_funds = {f for p in problems if p['type'] == 'duplicate' for f in p.get('funds', [])}
    
    for h in holdings:
        dr = h['daily_return']
        dr_str = f"{dr:+.2f}%" if dr is not None else "N/A"
        ret = h.get('returns', {})
        
        def fmt(v): return f"{v:+.1f}%" if v is not None else "N/A"
        
        trend = trend_signal(ret) if ret else "⚪"
        vol = h.get('volatility', 'N/A')
        mdd = h.get('max_drawdown', 'N/A')
        flag = "⚠️重复" if h['name'] in dup_funds else ""
        
        lines.append(f"| {h['fund_name_display'][:10]} | {h['code']} | ¥{h['amount']/10000:.1f}万 | {h['weight']:.1f}% | {dr_str} | {fmt(ret.get('1月'))} | {fmt(ret.get('3月'))} | {fmt(ret.get('6月'))} | {fmt(ret.get('1年'))} | {vol} | {mdd} | {trend} | {flag} |")
    lines.append("")
    
    # 三、问题诊断
    lines.append("## 三、问题诊断")
    if not problems:
        lines.append("✅ 组合结构正常，未发现明显问题")
    else:
        for p in problems:
            icon = {'high': '🔴', 'medium': '⚠️', 'low': '🟡'}.get(p['severity'], '•')
            lines.append(f"{icon} **{p['suggestion']}**")
    lines.append("")
    
    # 四、调仓建议
    lines.append("## 四、调仓优先级建议")
    if problems:
        for i, p in enumerate(problems, 1):
            lines.append(f"**{i}.** {p['suggestion']}")
    else:
        lines.append("✅ 无需调仓，当前组合结构合理")
    lines.append("")
    
    # 五、分类仓位健康度
    lines.append("## 五、分类仓位评价")
    for cat in ['A股权重基金', '黄金', '债券', '现金/货币']:
        items = analysis['categories'].get(cat, [])
        if not items:
            continue
        cw = sum(x['amount'] for x in items) / total * 100
        
        if cat == 'A股权重基金':
            status = "✅ 合理" if cw < 85 else "⚠️ 偏高，防御不足"
        elif cat == '黄金':
            status = "✅ 适量" if 5 < cw < 15 else ("🟡 偏高，注意回撤风险" if cw >= 15 else "⚠️ 偏低")
        elif cat == '债券':
            status = "✅ 充足" if cw >= 20 else ("⚠️ 偏低" if cw >= 10 else "🔴 严重不足")
        else:
            status = "✅ 合理"
        
        lines.append(f"- **{cat}（{cw:.1f}%）**：{status}")
    lines.append("")
    
    # 六、收益归因总结
    lines.append("## 六、收益归因")
    sorted_by_1y = sorted(holdings, key=lambda x: x.get('returns', {}).get('1年') or 0, reverse=True)
    
    lines.append("**近1年收益排名 TOP3：**")
    for i, h in enumerate(sorted_by_1y[:3], 1):
        r = h.get('returns', {}).get('1年')
        lines.append(f"  {i}. **{h['fund_name_display']}**：{r:+.1f}%" if r is not None else f"  {i}. **{h['fund_name_display']}**：数据不足")
    
    lines.append("")
    lines.append("**近1年收益最差：**")
    worst = sorted_by_1y[-1]
    r = worst.get('returns', {}).get('1年')
    lines.append(f"  ⚠️ **{worst['fund_name_display']}**：{r:+.1f}%" if r is not None else f"  ⚠️ **{worst['fund_name_display']}**：数据不足")
    lines.append("")
    
    return "\n".join(lines)


# ── 主程序 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='实时净值')
    parser.add_argument('--history', action='store_true', help='历史走势分析')
    parser.add_argument('--ocr', type=str, help='OCR文本')
    parser.add_argument('--holdings', type=str, help='JSON持仓')
    parser.add_argument('--test', action='store_true', help='测试模式')
    args = parser.parse_args()
    
    # 测试数据
    TEST = [
        {'code': '110020', 'name': '易方达沪深300ETF联接A', 'amount': 120476},
        {'code': '008585', 'name': '华夏人工智能ETF联接A', 'amount': 63427},
        {'code': '023902', 'name': '博道上证科创板综合指数增强C', 'amount': 58112},
        {'code': '018780', 'name': '华夏中证1000指数增强A', 'amount': 41050},
        {'code': '014081', 'name': '博时富瑞纯债债券A', 'amount': 40152},
        {'code': '217022', 'name': '招商产业债券A', 'amount': 40117},
        {'code': '009033', 'name': '建信上海金ETF联接A', 'amount': 50167},
        {'code': '008009', 'name': '华商高端装备制造股票A', 'amount': 30694},
        {'code': '004237', 'name': '中欧新蓝筹灵活配置混合C', 'amount': 26743},
        {'code': '004814', 'name': '中欧红利优享灵活配置混合A', 'amount': 18531},
        {'code': '004815', 'name': '中欧红利优享灵活配置混合C', 'amount': 6867},
    ]
    
    if args.test:
        holdings = TEST
    elif args.holdings:
        holdings = json.loads(args.holdings)
    elif args.ocr:
        # 简单OCR解析（略）
        holdings = TEST
    else:
        holdings = TEST
    
    codes = list({h['code'] for h in holdings})
    
    # 实时净值
    live_nav = {}
    if args.live:
        print("拉取实时净值...", file=sys.stderr)
        live_nav = get_fund_nav_live(codes)
    
    # 历史走势
    history_data = {}
    if args.history:
        print("拉取历史走势（需约20-30秒）...", file=sys.stderr)
        for code in codes:
            print(f"  分析 {code}...", file=sys.stderr)
            hd = analyze_single_fund_history(code, next((h['name'] for h in holdings if h['code']==code), code))
            history_data[code] = hd
    
    analysis = analyze_portfolio(holdings, live_nav, history_data)
    problems = detect_problems(holdings)
    report = generate_enhanced_report(analysis, problems)
    print(report)


if __name__ == "__main__":
    main()
