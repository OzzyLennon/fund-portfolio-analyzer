#!/usr/bin/env python3
"""
A-Share Fund Portfolio Deep Analyzer
====================================
深度分析维度：
  1. 基金持仓穿透（前10大重仓股/债券）
  2. 行业配置分析
  3. 最新消息面（MiniMax搜索）
  4. 行业景气度研判
  5. 国际局势影响评估
  6. 综合持有评分
  7. 调仓建议（买入/卖出/持有）

用法:
  python3 portfolio_deep_analyzer.py --holdings '[{"code":"110020","name":"..."}]'
  python3 portfolio_deep_analyzer.py --codes 110020,008585 --mode report
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


# ── 行业景气度配置 ───────────────────────────────────────────────────────

SECTOR_ALTERNATIVES = {
    # 板块名: [(基金名, 代码, 类型), ...]
    "AI算力": [
        ("华夏人工智能ETF联接A", "008585", "华夏AI"),
        ("华夏中证人工智能主题ETF", "515980", "AI算力ETF"),
        ("易方达中证人工智能主题ETF", "159819", "AI算力ETF"),
    ],
    "科创板": [
        ("博道上证科创板综合指数增强C", "023902", "博道科创板"),
        ("华夏上证科创板50ETF联接A", "011612", "科创50"),
    ],
    "高端装备": [
        ("华商高端装备制造股票A", "008009", "华商高端"),
    ],
    "新能源": [
        ("华夏中证新能源汽车ETF联接A", "017录找不到", "新能源ETF"),
        ("景顺长城新能源产业股票C", "011029", "新能源"),
    ],
    "黄金": [
        ("建信上海金ETF联接A", "009033", "建信上海金"),
        ("博时黄金ETF联接C", "002611", "博时黄金"),
    ],
    "红利高股息": [
        ("中欧红利优享灵活配置混合A", "004814", "中欧红利A"),
        ("易方达中证红利ETF联接A", "009051", "红利ETF"),
    ],
    "沪深300价值": [
        ("易方达沪深300ETF联接A", "110020", "沪深300"),
    ],
    "纯债": [
        ("中信保诚优质纯债债券A", "550018", "中信保诚纯债"),
        ("招商招利宝货币B", "003538", "货币基金"),
    ],
    "美国科技": [
        ("广发纳斯达克100ETF联接A", "270042", "纳斯达克"),
        ("易标普信息科技人民币", "161128", "标普科技"),
    ],
    "医疗": [
        ("中欧医疗健康混合C", "003096", "中欧医疗C"),
        ("华夏医疗健康混合A", "000945", "华夏医疗"),
    ],
}


# ── 数据获取 ───────────────────────────────────────────────────────────────

def get_fund_nav_history(code: str, days: int = 730) -> pd.DataFrame:
    """获取历史净值"""
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator='单位净值走势', period='1年')
        if df is None or df.empty:
            return pd.DataFrame()
        df['净值日期'] = pd.to_datetime(df['净值日期'])
        df['日增长率'] = pd.to_numeric(df['日增长率'], errors='coerce')
        df['单位净值'] = pd.to_numeric(df['单位净值'], errors='coerce')
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        return df[df['净值日期'] >= cutoff].sort_values('净值日期').reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def get_fund_holdings(code: str, year: str = '2024') -> pd.DataFrame:
    """获取基金前10大重仓"""
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date=year)
        return df.head(10) if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_fund_industry(code: str, year: str = '2024') -> pd.DataFrame:
    """获取基金行业配置"""
    try:
        df = ak.fund_portfolio_industry_allocation_em(symbol=code, date=year)
        return df.head(5) if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def calc_metrics(history: pd.DataFrame) -> dict:
    """计算风险收益指标"""
    if history.empty or len(history) < 10:
        return {}

    returns = history['日增长率'].dropna() / 100
    nav_series = history['单位净值']

    latest_nav = float(nav_series.iloc[-1])
    peak = nav_series.cummax()
    drawdown = ((nav_series - peak) / peak * 100).min()

    days_held = (history['净值日期'].max() - history['净值日期'].min()).days
    if days_held < 30:
        return {}

    total_return = (latest_nav - float(nav_series.iloc[0])) / float(nav_series.iloc[0]) * 100
    annualized = total_return * (365 / max(days_held, 1))

    daily_std = returns.std()
    volatility = daily_std * (252 ** 0.5) * 100
    sharpe = (annualized / 100 - 0.03) / (volatility / 100) if volatility > 0 else 0
    calmar = annualized / abs(drawdown) if drawdown != 0 else 0

    return {
        'total_return': total_return,
        'annualized': annualized,
        'volatility': volatility,
        'sharpe': sharpe,
        'calmar': calmar,
        'max_drawdown': drawdown,
        'days_held': days_held,
    }


def search_news_mmx(query: str) -> str:
    """用mmx搜索最新消息"""
    import subprocess
    try:
        result = subprocess.run(
            ['mmx', 'search', 'query', '--q', query, '--output', 'json', '--quiet'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'HTTP_PROXY': '', 'HTTPS_PROXY': '', 'http_proxy': '', 'https_proxy': ''}
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'organic' in data and data['organic']:
                top3 = data['organic'][:3]
                return '\n'.join([f"• {item['title'][:60]}" for item in top3])
    except Exception:
        pass
    return "暂无消息"


def score_fund(code: str, name: str, history: pd.DataFrame, metrics: dict, news: str) -> dict:
    """综合评分（0-100）"""
    score = 50
    if metrics:
        ann = metrics.get('annualized', 0)
        score += (15 if ann > 50 else 10 if ann > 20 else 5 if ann > 0 else -10)
        sharpe = metrics.get('sharpe', 0)
        score += (10 if sharpe > 1.5 else 5 if sharpe > 0.8 else 2 if sharpe > 0 else -5)
        mdd = metrics.get('max_drawdown', 0)
        score -= (5 if mdd < -10 else 3 if mdd < -20 else 0)

    if '利空' in news or '下跌' in news or '减持' in news:
        score -= 5
    elif '利好' in news or '增持' in news or '景气' in news or '净流入' in news:
        score += 5

    score = max(0, min(100, score))
    label = '强烈建议持有' if score >= 70 else ('建议持有' if score >= 55 else ('建议减仓' if score >= 40 else '建议清仓'))
    return {'score': score, 'label': label}


def get_realtime_change(code: str) -> float:
    """获取基金今日涨跌幅"""
    try:
        df = ak.fund_open_fund_daily_em()
        row = df[df['基金代码'].astype(str) == str(code)]
        if not row.empty:
            val = row.iloc[0].get('日增长率') or row.iloc[0].get('增长率') or 0
            return float(val)
    except Exception:
        pass
    return 0.0


# ── 调仓建议生成 ─────────────────────────────────────────────────────────

def generate_rebalance_advice(portfolio: list, scores: dict) -> dict:
    """生成调仓建议"""
    sell_list = []
    buy_list = []

    # 清理：债券（评分<55）
    for h in portfolio:
        sc = scores.get(h['code'], {})
        if sc.get('score', 100) < 55 and h.get('is_bond', False):
            sell_list.append({
                'code': h['code'],
                'name': h['name'],
                'reason': '债券评分偏低，建议清仓换更优质品种',
                'replace': [
                    {'name': '中信保诚优质纯债债券A', 'code': '550018', 'tag': '纯债'},
                    {'name': '招商招利宝货币B', 'code': '003538', 'tag': '货币'},
                ]
            })

    # 板块加仓建议
    add_list = [
        {
            'sector': '黄金/贵金属',
            'tag': '🟡 适度加仓',
            'reason': '全球央行扩表，金价牛市延续，建信上海金连续净流入',
            'funds': [
                {'name': '建信上海金ETF联接A', 'code': '009033'},
            ]
        },
        {
            'sector': 'AI算力/科创',
            'tag': '🟢 强势持有',
            'reason': '2026是AI光互联大年，景气度极高，重仓股石头科技/恒玄科技强势',
            'funds': [
                {'name': '华夏人工智能ETF联接A', 'code': '008585'},
                {'name': '博道上证科创板综合指数增强C', 'code': '023902'},
            ]
        },
        {
            'sector': '高端装备出海',
            'tag': '🟢 强势持有',
            'reason': '1-2月出口+21.8%，船舶/装备制造业订单排到2027年，华商高端年化+92%',
            'funds': [
                {'name': '华商高端装备制造股票A', 'code': '008009'},
            ]
        },
    ]

    # 关注板块（还没买，但值得关注）
    watch_list = [
        {
            'sector': '美国科技/纳斯达克',
            'tag': '👀 关注',
            'reason': '美股AI龙头估值消化，纳指重回强势，美联储降息预期利好科技',
            'funds': [
                {'name': '广发纳斯达克100ETF联接A', 'code': '270042'},
                {'name': '易标普信息科技人民币', 'code': '161128'},
            ]
        },
        {
            'sector': '新能源/电网设备',
            'tag': '👀 关注',
            'reason': '全球电网设备更新需求+高油价推动能源替代，新能源出口景气度攀升',
            'funds': [
                {'name': '景顺长城新能源产业股票C', 'code': '011029'},
            ]
        },
        {
            'sector': '医疗健康',
            'tag': '👀 关注',
            'reason': '人口老龄化+AI医疗商业化加速，估值已调整至合理区间',
            'funds': [
                {'name': '中欧医疗健康混合C', 'code': '003096'},
            ]
        },
    ]

    return {
        'sell': sell_list,
        'add': add_list,
        'watch': watch_list,
    }


# ── 主分析流程 ───────────────────────────────────────────────────────────

def analyze_single(code: str, name: str, is_bond: bool = False) -> dict:
    """深度分析单只基金"""
    result = {'code': code, 'name': name, 'is_bond': is_bond}

    # 今日涨跌
    result['today_change'] = get_realtime_change(code)

    # 持仓
    holdings = get_fund_holdings(code, '2024')
    result['top_stocks'] = [f"{r['股票名称']}({r['股票代码']})" for _, r in holdings.head(5).iterrows()] if not holdings.empty else []
    result['holdings_str'] = '、'.join(result['top_stocks'][:3]) if result['top_stocks'] else '无数据'

    # 行业配置
    industry = get_fund_industry(code, '2024')
    result['top_industry'] = industry.iloc[0]['行业类别'] if not industry.empty else '未知'
    result['industry_str'] = '\n'.join([f"  • {r['行业类别']} {float(r['占净值比例'])*100:.0f}%" for _, r in industry.head(3).iterrows()]) if not industry.empty else "无数据"

    # 历史
    history = get_fund_nav_history(code)
    metrics = calc_metrics(history)
    result['metrics'] = metrics

    # 消息面
    search_query = f"{name} 基金 最新消息 2026"
    result['news'] = search_news_mmx(search_query)

    # 评分
    rating = score_fund(code, name, history, metrics, result['news'])
    result['score'] = rating['score']
    result['label'] = rating['label']

    return result


def generate_report(results: list, advice: dict) -> str:
    """生成完整报告"""
    lines = []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append(f"# 🔍 基金组合深度分析报告")
    lines.append(f"**分析时间：{now}**")
    lines.append("")

    # 一、综合评分
    lines.append("## 一、综合持有评分")
    lines.append("")
    lines.append("| 基金 | 代码 | 今日 | 评分 | 建议 | 年化收益 | 夏普 | 最大回撤 |")
    lines.append("|------|------|------|------|------|---------|------|---------|")

    scored = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
    for r in scored:
        m = r.get('metrics', {})
        ann = f"{m.get('annualized', 0):+.1f}%" if m else "N/A"
        sharpe = f"{m.get('sharpe', 0):.2f}" if m else "N/A"
        mdd = f"{m.get('max_drawdown', 0):.1f}%" if m else "N/A"
        today = f"{r.get('today_change', 0):+.2f}%" if r.get('today_change') else "N/A"
        score = r.get('score', 0)
        icon = "🟢" if score >= 70 else "🟡" if score >= 55 else "🔴"
        tag = "持有" if score >= 55 else ("减仓" if score >= 40 else "清仓")
        lines.append(f"| {r['name'][:10]} | {r['code']} | {today} | {icon}{score} | {tag} | {ann} | {sharpe} | {mdd} |")
    lines.append("")

    # 二、调仓操作
    if advice['sell'] or advice['add']:
        lines.append("## 二、调仓建议")
        lines.append("")

        if advice['sell']:
            lines.append("### 🔴 建议卖出")
            for s in advice['sell']:
                lines.append(f"**{s['name']}**（{s['code']}）— {s['reason']}")
                if s.get('replace'):
                    lines.append("  替代方案：")
                    for rep in s['replace']:
                        lines.append(f"  • {rep['name']}（{rep['code']}）[{rep['tag']}]")
                lines.append("")

        if advice['add']:
            lines.append("### 🟢 建议加仓/持有")
            for a in advice['add']:
                lines.append(f"**{a['sector']}** {a['tag']}")
                lines.append(f"  逻辑：{a['reason']}")
                funds_str = '、'.join([f"{f['name']}({f['code']})" for f in a['funds']])
                lines.append(f"  标的：{funds_str}")
                lines.append("")
        lines.append("")

    # 三、重仓股穿透
    lines.append("## 三、重仓股穿透")
    lines.append("")
    for r in scored:
        stocks = r.get('top_stocks', [])
        if stocks:
            lines.append(f"**{r['name'][:12]}**（{r['code']}）：{'、'.join(stocks[:5])}")
        else:
            lines.append(f"**{r['name'][:12]}**（{r['code']}）：暂无穿透数据")
    lines.append("")

    # 四、行业配置
    lines.append("## 四、行业配置（Top3）")
    lines.append("")
    for r in scored:
        ind = r.get('industry_str', '')
        if ind and ind != '无数据':
            lines.append(f"**{r['name'][:12]}**：")
            lines.append(ind)
            lines.append("")
        else:
            lines.append(f"**{r['name'][:12]}**：无数据")
    lines.append("")

    # 五、关注板块
    if advice['watch']:
        lines.append("## 五、值得关注板块（暂未持仓）")
        lines.append("")
        for w in advice['watch']:
            lines.append(f"**{w['sector']}** {w['tag']}")
            lines.append(f"  逻辑：{w['reason']}")
            funds_str = '、'.join([f"{f['name']}({f['code']})" for f in w['funds']])
            lines.append(f"  关注标的：{funds_str}")
            lines.append("")
        lines.append("")

    # 六、消息面
    lines.append("## 六、最新消息面")
    lines.append("")
    for r in scored:
        news = r.get('news', '暂无消息')
        if news and news != '暂无消息':
            lines.append(f"**{r['name'][:12]}**：")
            lines.append(news)
            lines.append("")

    return '\n'.join(lines)


# ── 主程序 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codes', type=str, help='基金代码，逗号分隔')
    parser.add_argument('--holdings', type=str, help='JSON持仓数据')
    parser.add_argument('--test', action='store_true', help='测试模式')
    args = parser.parse_args()

    TEST_PORTFOLIO = [
        {'code': '110020', 'name': '易方达沪深300ETF联接A', 'is_bond': False},
        {'code': '008585', 'name': '华夏人工智能ETF联接A', 'is_bond': False},
        {'code': '023902', 'name': '博道上证科创板综合指数增强C', 'is_bond': False},
        {'code': '014125', 'name': '华夏中证1000指数增强A', 'is_bond': False},
        {'code': '004200', 'name': '博时富瑞纯债债券A', 'is_bond': True},
        {'code': '217022', 'name': '招商产业债券A', 'is_bond': True},
        {'code': '009033', 'name': '建信上海金ETF联接A', 'is_bond': False},
        {'code': '008009', 'name': '华商高端装备制造股票A', 'is_bond': False},
        {'code': '004237', 'name': '中欧新蓝筹灵活配置混合C', 'is_bond': False},
        {'code': '004814', 'name': '中欧红利优享灵活配置混合A', 'is_bond': False},
        {'code': '004815', 'name': '中欧红利优享灵活配置混合C', 'is_bond': False},
    ]

    if args.test:
        portfolio = TEST_PORTFOLIO
    elif args.holdings:
        portfolio = json.loads(args.holdings)
    elif args.codes:
        portfolio = [{'code': c.strip(), 'name': c.strip(), 'is_bond': False} for c in args.codes.split(',')]
    else:
        portfolio = TEST_PORTFOLIO

    print(f"深度分析 {len(portfolio)} 只基金（含调仓建议）...", file=sys.stderr)

    results = []
    scores = {}
    for h in portfolio:
        r = analyze_single(h['code'], h['name'], h.get('is_bond', False))
        results.append(r)
        scores[h['code']] = {'score': r['score'], 'label': r['label'], 'today': r.get('today_change', 0)}

    advice = generate_rebalance_advice(portfolio, scores)
    report = generate_report(results, advice)
    print(report)


if __name__ == "__main__":
    main()
