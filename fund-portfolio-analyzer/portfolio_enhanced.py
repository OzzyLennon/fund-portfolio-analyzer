#!/usr/bin/env python3
"""
A-Share Fund Portfolio Analyzer - Enhanced v6
===========================================
v6 新增功能：
  1. 同类排名：基金在同类中的百分位排名
  2. 费率精算：申赎费+管理费影响后的实际收益率
  3. 组合优化：Mean-Variance 最优权重（最大夏普）
  4. Sortino比率：下行风险指标（内置v5）
  5. 历史最大回撤区间：回撤起止日期
  6. 滚动夏普（12月）：近12个月滚动年化夏普
  7. 资金流向：北向资金 + ETF净流入（市场情绪）
"""

import sys, os, json, re, argparse, warnings, datetime
warnings.filterwarnings('ignore')
for v in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(v, None)

import akshare as ak
import pandas as pd
import numpy as np


# ── 基金类型分类 ───────────────────────────────────────────────────────

FUND_TYPE_MAP = {
    'ETF': ['ETF', 'ETF联接', '交易型'],
    'index': ['指数'],
    'stock': ['股票', '产业', '制造', '科技'],
    'mixed': ['混合', '蓝筹', '优享', '灵活配置'],
    'bond': ['债券', '纯债'],
    'gold': ['黄金', '上海金', '金ETF'],
    'money': ['货币', '现金'],
}

def classify_fund(name, code):
    n = name + code
    for ft, kws in FUND_TYPE_MAP.items():
        for kw in kws:
            if kw in n:
                return ft
    return 'mixed'


# ── 数据获取 ───────────────────────────────────────────────────────────

def get_fund_nav_history(code, days=730):
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


def get_fund_type_rank(code, fund_type, period='今年来'):
    try:
        type_map = {
            'stock': '股票型', 'mixed': '混合型', 'bond': '债券型',
            'ETF': '指数型', 'index': '指数型', 'gold': 'QDII', 'money': '货币型',
        }
        symbol = type_map.get(fund_type, '混合型')
        df = ak.fund_open_fund_rank_em(symbol=symbol)
        if df is None or df.empty:
            return {'percentile': None, 'rank': None, 'total': None}
        df[period] = pd.to_numeric(df[period], errors='coerce')
        df = df.dropna(subset=[period]).drop_duplicates('基金代码')
        n = len(df)
        df = df.sort_values(period, ascending=False).reset_index(drop=True)
        match = df[df['基金代码'].astype(str) == str(code)]
        if match.empty:
            return {'percentile': None, 'rank': None, 'total': n}
        rank = df.index[df['基金代码'].astype(str) == str(code)].tolist()[0] + 1
        percentile = (n - rank) / n * 100
        return {'percentile': round(percentile, 1), 'rank': rank, 'total': n, 'period': period}
    except Exception:
        return {'percentile': None, 'rank': None, 'total': None}


def get_fund_fee(code, hold_days=365):
    result = {'purchase_fee': None, 'redeem_fee': None, 'manage_fee': None, 'total_annual_cost': None}
    try:
        try:
            df = ak.fund_fee_em(symbol=code, indicator='赎回费率')
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    term = str(row.get('适用期限', ''))
                    fee_str = str(row.get('赎回费率', '0%')).replace('%', '')
                    try:
                        fee = float(fee_str)
                    except ValueError:
                        fee = 0.0
                    if hold_days >= 730 and '730天' in term:
                        result['redeem_fee'] = fee
                        break
                    elif hold_days >= 365 and '365天' in term:
                        result['redeem_fee'] = fee
                    elif hold_days >= 7 and '7天' in term and result['redeem_fee'] is None:
                        result['redeem_fee'] = fee
        except Exception:
            pass
        type_fee = {'stock': 1.5, 'mixed': 1.2, 'bond': 0.6, 'ETF': 0.5, 'index': 0.5, 'gold': 0.8, 'money': 0.3}
        ft = classify_fund('', code)
        result['manage_fee'] = type_fee.get(ft, 1.2)
        result['total_annual_cost'] = result['manage_fee'] + (result['redeem_fee'] or 0)
        return result
    except Exception:
        return result


def get_north_flow() -> dict:
    """获取北向资金近5日净流入"""
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return {'trend': 'unknown', 'recent_5d': 0}
        df.columns = [str(c).strip() for c in df.columns]
        # 找到净买额列
        net_col = None
        for c in df.columns:
            if '\u51c0\u4e70' in c:
                net_col = c
                break
        if net_col is None:
            return {'trend': 'unknown', 'recent_5d': 0}
        df[net_col] = pd.to_numeric(df[net_col], errors='coerce')
        df = df.dropna(subset=[net_col]).tail(5)
        total = float(df[net_col].sum())
        if len(df) >= 2:
            recent = float(df[net_col].iloc[-1])
            prev = float(df[net_col].iloc[-2])
            trend = '流入' if recent > 0 else ('流出' if recent < 0 else '持平')
            if recent > prev:
                trend += '加速' if recent > 0 else '减缓'
            elif recent < prev:
                trend += '减缓' if recent > 0 else '加速'
        else:
            trend = 'unknown'
        return {'trend': trend, 'recent_5d': round(total, 2), 'today': round(float(df[净买_col].iloc[-1]), 2) if len(df) > 0 else 0}
    except Exception:
        return {'trend': 'unknown', 'recent_5d': 0}


# ── 指标计算 ───────────────────────────────────────────────────────────

def calc_metrics(history):
    """计算完整风险收益指标"""
    if history.empty or len(history) < 10:
        return {}
    returns = history['日增长率'].dropna() / 100
    nav_series = history['单位净值']
    latest_nav = float(nav_series.iloc[-1])
    peak = nav_series.cummax()
    dd = ((nav_series - peak) / peak * 100)
    max_dd = float(dd.min())
    max_dd_end_idx = int(dd.argmin())
    max_dd_start_idx = int(nav_series[:max_dd_end_idx+1].argmax())
    max_dd_start = history['净值日期'].iloc[max_dd_start_idx] if max_dd_start_idx < len(history) else history['净值日期'].iloc[0]
    max_dd_end = history['净值日期'].iloc[max_dd_end_idx]
    days_held = (history['净值日期'].max() - history['净值日期'].min()).days
    if days_held < 30:
        return {}
    total_return = (latest_nav - float(nav_series.iloc[0])) / float(nav_series.iloc[0]) * 100
    annualized = total_return * (365 / max(days_held, 1))
    daily_std = float(returns.std())
    volatility = daily_std * (252 ** 0.5) * 100
    sharpe = (annualized / 100 - 0.03) / (volatility / 100) if volatility > 0 else 0
    neg = returns[returns < 0]
    sortino = float((annualized / 100 - 0.03) / (float(neg.std()) * (252 ** 0.5))) if len(neg) > 2 else 0

    # 滚动12月夏普
    rolling_sharpe_12m = None
    if len(history) >= 252:
        window = history.tail(252).copy()
        win_returns = window['日增长率'].dropna() / 100
        if len(win_returns) >= 60:
            win_ann = float(win_returns.mean() * 252)
            win_vol = float(win_returns.std() * (252 ** 0.5) * 100)
            rolling_sharpe_12m = round((win_ann / 100 - 0.03) / (win_vol / 100), 2) if win_vol > 0 else 0

    return {
        'total_return': float(total_return),
        'annualized': float(annualized),
        'volatility': float(volatility),
        'sharpe': float(sharpe),
        'sortino': float(sortino),
        'max_drawdown': max_dd,
        'max_dd_start': str(max_dd_start.date()) if hasattr(max_dd_start, 'date') else str(max_dd_start)[:10],
        'max_dd_end': str(max_dd_end.date()) if hasattr(max_dd_end, 'date') else str(max_dd_end)[:10],
        'days_held': days_held,
        'rolling_sharpe_12m': rolling_sharpe_12m,
    }


# ── 组合优化 ───────────────────────────────────────────────────────────

def optimize_portfolio(results):
    try:
        from scipy.optimize import minimize
    except ImportError:
        return {}
    valid = []
    for r in results:
        m = r.get('metrics', {})
        if m and m.get('annualized', 0) > -50 and m.get('volatility', 0) > 0:
            valid.append({'code': r['code'], 'name': r['name'],
                'ret': m['annualized'] / 100, 'vol': m['volatility'] / 100, 'weight': 0})
    if len(valid) < 2:
        return {}
    n = len(valid)
    rets = np.array([v['ret'] for v in valid])
    vols = np.array([v['vol'] for v in valid])
    cov = np.diag(vols ** 2)

    def neg_sharpe(w):
        pr = float(w @ rets)
        pv = float(np.sqrt(w @ cov @ w + 1e-8))
        return -(pr - 0.03) / pv if pv > 1e-6 else 0

    cons = {'type': 'eq', 'fun': lambda w: float(sum(w)) - 1}
    bounds = [(0.0, 1.0)] * n
    w0 = np.ones(n) / n
    res = minimize(neg_sharpe, w0, method='SLSQP', bounds=bounds, constraints=cons)
    if res.success:
        w = res.x
        opt_ret = float(w @ rets)
        opt_vol = float(np.sqrt(w @ cov @ w + 1e-8))
        for i, v in enumerate(valid):
            v['weight'] = round(float(w[i]) * 100, 1)
        valid_sorted = sorted(valid, key=lambda x: x['weight'], reverse=True)
        return {
            'success': True,
            'weights': valid_sorted,
            'expected_return': round(opt_ret * 100, 2),
            'expected_volatility': round(opt_vol * 100, 2),
            'expected_sharpe': round((opt_ret - 0.03) / opt_vol, 2) if opt_vol > 1e-6 else 0,
        }
    return {}


# ── 综合评分 ───────────────────────────────────────────────────────────


def optimize_portfolio_multi(results, money_fund_ratio=0.10):
    """
    Mean-Variance 组合优化（最大夏普）
    money_fund_ratio: 货币基金最低配置比例（0=激进, 0.05=5%, 0.10=10%, 0.20=稳健）
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        return []

    valid = []
    for r in results:
        m = r.get('metrics', {})
        if m and m.get('annualized', 0) > -50 and m.get('volatility', 0) > 0:
            valid.append({
                'code': r['code'], 'name': r['name'],
                'ret': m['annualized'] / 100,
                'vol': m['volatility'] / 100,
                'is_money': r.get('fund_type') == 'money',
                'weight': 0,
            })

    # 如果没有货币基金，用估算收益率注入
    has_money = any(v['is_money'] for v in valid)
    if not has_money:
        valid.append({'code': 'MONEY', 'name': '货币基金(建议配置)', 'ret': 0.0165, 'vol': 0.001, 'is_money': True, 'weight': 0})

    n = len(valid)
    rets = np.array([v['ret'] for v in valid])
    vols = np.array([v['vol'] for v in valid])
    cov = np.diag(vols ** 2)
    money_idx = next((i for i, v in enumerate(valid) if v['is_money']), None)

    def run_opt(min_money):
        def neg_sharpe(w):
            pr = float(w @ rets)
            pv = float(np.sqrt(w @ cov @ w + 1e-8))
            return -(pr - 0.03) / pv if pv > 1e-6 else 0
        bounds = [(0.0, 1.0)] * n
        if money_idx is not None and min_money > 0:
            bounds[money_idx] = (min_money, 1.0)
        cons = {'type': 'eq', 'fun': lambda w: float(sum(w)) - 1}
        w0 = np.ones(n) / n
        if money_idx is not None:
            w0[money_idx] = min_money
        res = minimize(neg_sharpe, w0, method='SLSQP', bounds=bounds, constraints=cons)
        if res.success:
            w = res.x
            opt_ret = float(w @ rets)
            opt_vol = float(np.sqrt(w @ cov @ w + 1e-8))
            opt_sharpe = (opt_ret - 0.03) / opt_vol if opt_vol > 1e-6 else 0
            for i, v in enumerate(valid):
                v['weight'] = round(float(w[i]) * 100, 1)
            weights = sorted(valid, key=lambda x: x['weight'], reverse=True)
            return {
                'min_money': min_money,
                'label': '激进(0%货基)' if min_money == 0 else ('5%货币基金' if min_money == 0.05 else ('10%货币基金' if min_money == 0.10 else ('15%货币基金' if min_money == 0.15 else '20%稳健'))),
                'expected_return': round(opt_ret * 100, 2),
                'expected_volatility': round(opt_vol * 100, 2),
                'expected_sharpe': round(opt_sharpe, 2),
                'weights': [{'name': v['name'][:14], 'weight': v['weight'], 'code': v['code']} for v in weights if v['weight'] > 0.3],
            }
        return None

    configs = [0, 0.05, 0.10, 0.15, 0.20]
    results_list = []
    for cfg in configs:
        r = run_opt(cfg)
        if r:
            results_list.append(r)
    return results_list


def score_fund(metrics, fee, rank):
    score = 50
    if metrics:
        ann = metrics.get('annualized', 0)
        score += (15 if ann > 50 else 10 if ann > 20 else 5 if ann > 0 else -10)
        sharpe = metrics.get('sharpe', 0)
        score += (10 if sharpe > 1.5 else 5 if sharpe > 0.8 else 2 if sharpe > 0 else -5)
        rolling = metrics.get('rolling_sharpe_12m')
        if rolling is not None:
            score += (5 if rolling > 1.5 else 2 if rolling > 0.5 else -3)
    if fee.get('total_annual_cost'):
        cost = fee['total_annual_cost']
        score -= (8 if cost > 3 else 4 if cost > 2 else 0)
    if rank.get('percentile'):
        pct = rank['percentile']
        score += (8 if pct >= 90 else 4 if pct >= 70 else 2 if pct >= 50 else 0)
    score = max(0, min(100, score))
    label = '强烈建议持有' if score >= 70 else ('建议持有' if score >= 55 else ('建议减仓' if score >= 40 else '建议清仓'))
    return {'score': score, 'label': label}


# ── 主分析 ─────────────────────────────────────────────────────────────

def analyze_single(code, name, rank_period='今年来'):
    r = {'code': code, 'name': name}
    try:
        df_d = ak.fund_open_fund_daily_em()
        row = df_d[df_d['基金代码'].astype(str) == str(code)]
        r['today_change'] = float(row.iloc[0].get('日增长率', 0)) if not row.empty else 0.0
    except Exception:
        r['today_change'] = 0.0
    ft = classify_fund(name, code)
    r['fund_type'] = ft
    hist = get_fund_nav_history(code)
    metrics = calc_metrics(hist)
    r['metrics'] = metrics
    rank = get_fund_type_rank(code, ft, period=rank_period)
    r['rank'] = rank
    fee = get_fund_fee(code, hold_days=365)
    r['fee'] = fee
    if metrics and fee.get('total_annual_cost'):
        r['net_annualized'] = round(metrics.get('annualized', 0) - fee['total_annual_cost'], 2)
    else:
        r['net_annualized'] = metrics.get('annualized', 0) if metrics else 0
    rating = score_fund(metrics, fee, rank)
    r['score'] = rating['score']
    r['label'] = rating['label']
    return r


# ── 报告生成 ───────────────────────────────────────────────────────────

def generate_report(results, opt, north_flow):
    lines = []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append("# 📊 基金组合增强分析报告 v6")
    lines.append("**时间：" + now + "**")
    lines.append("")

    # 市场情绪
    lines.append("## 🌐 市场资金情绪")
    lines.append("")
    nf = north_flow
    flow_icon = "🟢" if nf.get('today', 0) > 0 else "🔴" if nf.get('today', 0) < 0 else "⚪"
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append("| 今日北向资金 | " + flow_icon + " " + str(nf.get('today', 0)) + " 亿 |")
    lines.append("| 近5日北向净流入 | " + str(nf.get('recent_5d', 0)) + " 亿 |")
    lines.append("| 趋势判断 | " + str(nf.get('trend', 'unknown')) + " |")
    lines.append("")

    # 综合评分
    lines.append("## 一、综合持有评分")
    lines.append("")
    lines.append("| 基金 | 类型 | 评分 | 建议 | 年化(含费) | 夏普 | 滚动12月夏普 | 同类前% |")
    lines.append("|------|------|------|------|---------|------|------------|---------|")
    scored = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
    for r in scored:
        m = r.get('metrics', {})
        ann = str(round(m.get('annualized', 0), 1)) + '%'
        net = str(round(r.get('net_annualized', 0), 1)) + '%'
        sharpe = str(round(m.get('sharpe', 0), 2)) if m else 'N/A'
        rolling = str(m.get('rolling_sharpe_12m', 'N/A')) if m.get('rolling_sharpe_12m') is not None else 'N/A'
        pct = str(r['rank'].get('percentile', 'N/A')) if r.get('rank', {}).get('percentile') else 'N/A'
        score = r.get('score', 0)
        icon = "🟢" if score >= 70 else "🟡" if score >= 55 else "🔴"
        tag = "持有" if score >= 55 else ("减仓" if score >= 40 else "清仓")
        lines.append("| " + r['name'][:10] + " | " + r.get('fund_type','mixed') + " | " + icon + str(score) + " | " + tag + " | " + net + " | " + sharpe + " | " + rolling + " | " + pct + "% |")
    lines.append("")

    # 同类排名
    lines.append("## 二、同类排名详情")
    lines.append("")
    lines.append("| 基金 | 类型 | 同类前% | 排名/总计 |")
    lines.append("|------|------|---------|---------|")
    for r in scored:
        rank = r.get('rank', {})
        pct = str(rank.get('percentile', 'N/A')) if rank.get('percentile') else 'N/A'
        total = str(rank.get('total', '?'))
        rnk = str(rank.get('rank', '?'))
        lines.append("| " + r['name'][:10] + " | " + r.get('fund_type','mixed') + " | " + pct + "% | " + rnk + "/" + total + " |")
    lines.append("")

    # 费率
    lines.append("## 三、费率明细")
    lines.append("")
    lines.append("| 基金 | 管理费/年 | 赎回费(1年) | 总年化成本 | 实际年化收益 |")
    lines.append("|------|---------|-----------|-----------|-------------|")
    for r in scored:
        fee = r.get('fee', {})
        mng = str(fee.get('manage_fee', 'N/A')) + '%' if fee.get('manage_fee') else 'N/A'
        reed = (str(round(fee.get('redeem_fee', 0), 1)) + '%') if fee.get('redeem_fee') is not None else 'N/A'
        total = (str(round(fee.get('total_annual_cost', 0), 2)) + '%') if fee.get('total_annual_cost') else 'N/A'
        net = str(round(r.get('net_annualized', 0), 2)) + '%'
        lines.append("| " + r['name'][:10] + " | " + mng + " | " + reed + " | " + total + " | " + net + " |")
    lines.append("")

    # 组合优化（多版本对比）
    multi_results = opt if isinstance(opt, list) else []
    if multi_results:
        lines.append("## 四、组合优化对比（Mean-Variance 最大夏普）")
        lines.append("")
        lines.append("| 方案 | 货基占比 | 预期收益 | 波动率 | 夏普比率 |")
        lines.append("|------|---------|---------|--------|---------|")
        for r in multi_results:
            money_pct = str(int(r['min_money'] * 100)) + '%'
            lines.append("| **" + r['label'] + "** | " + money_pct + " | " + str(r['expected_return']) + "% | " + str(r['expected_volatility']) + "% | " + str(r['expected_sharpe']) + " |")
        lines.append("")

        # 默认选10%方案详细展示
        default_plan = next((r for r in multi_results if r['min_money'] == 0.10), multi_results[0])
        lines.append("**建议方案：" + default_plan['label'] + "**")
        lines.append("")
        lines.append("| 基金 | 建议仓位 |")
        lines.append("|------|---------|")
        for v in default_plan['weights']:
            lines.append("| " + v['name'][:14] + " | **" + str(v['weight']) + "%** |")
        lines.append("")
    elif opt.get('success'):
        lines.append("## 四、组合优化（Mean-Variance 最大夏普）")
        lines.append("")
        lines.append("**预期组合收益：** " + str(opt['expected_return']) + "%/年")
        lines.append("**预期波动率：** " + str(opt['expected_volatility']) + "%")
        lines.append("**预期夏普比率：** " + str(opt['expected_sharpe']))
        lines.append("")
        lines.append("| 基金 | 优化权重 |")
        lines.append("|------|---------|")
        for v in opt['weights']:
            if v['weight'] > 0.5:
                lines.append("| " + v['name'][:12] + " | **" + str(v['weight']) + "%** |")
        lines.append("")
    else:
        lines.append("## 四、组合优化")
        lines.append("*数据不足，跳过优化*")
        lines.append("")

    # 风险指标（含最大回撤区间）
    lines.append("## 五、风险指标（含最大回撤区间）")
    lines.append("")
    lines.append("| 基金 | 年化收益 | 波动率 | Sortino | 夏普(2年) | 滚动夏普 | 最大回撤 | 回撤区间 |")
    lines.append("|------|---------|--------|---------|---------|---------|---------|---------|")
    for r in scored:
        m = r.get('metrics', {})
        ann = str(round(m.get('annualized', 0), 1)) + '%'
        vol = str(round(m.get('volatility', 0), 1)) + '%'
        sortino = str(round(m.get('sortino', 0), 2))
        sharpe2y = str(round(m.get('sharpe', 0), 2))
        rolling = str(m.get('rolling_sharpe_12m', 'N/A')) if m.get('rolling_sharpe_12m') is not None else 'N/A'
        mdd = str(round(m.get('max_drawdown', 0), 1)) + '%'
        dd_period = (m.get('max_dd_start', '?') + ' ~ ' + m.get('max_dd_end', '?')) if m.get('max_dd_start') else 'N/A'
        lines.append("| " + r['name'][:10] + " | " + ann + " | " + vol + " | " + sortino + " | " + sharpe2y + " | " + rolling + " | " + mdd + " | " + dd_period + " |")
    lines.append("")
    return '\n'.join(lines)


# ── 主程序 ─────────────────────────────────────────────────────────────

PORTFOLIO_DEFAULT = [
    {'code': '110020', 'name': '易方达沪深300ETF联接A'},
    {'code': '008585', 'name': '华夏人工智能ETF联接A'},
    {'code': '023902', 'name': '博道上证科创板综合指数增强C'},
    {'code': '014125', 'name': '华夏中证1000指数增强A'},
    {'code': '004200', 'name': '博时富瑞纯债债券A'},
    {'code': '217022', 'name': '招商产业债券A'},
    {'code': '009033', 'name': '建信上海金ETF联接A'},
    {'code': '008009', 'name': '华商高端装备制造股票A'},
    {'code': '004237', 'name': '中欧新蓝筹灵活配置混合C'},
    {'code': '004814', 'name': '中欧红利优享灵活配置混合A'},
    {'code': '004815', 'name': '中欧红利优享灵活配置混合C'},
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--holdings', type=str)
    p.add_argument('--codes', type=str)
    p.add_argument('--all', action='store_true')
    p.add_argument('--rank-period', type=str, default='今年来')
    p.add_argument('--money-fund', type=str, default='10', help='货币基金最低配置比例（0/5/10/15/20），默认10')
    args = p.parse_args()

    if args.all:
        portfolio = PORTFOLIO_DEFAULT
    elif args.holdings:
        portfolio = json.loads(args.holdings)
    elif args.codes:
        portfolio = [{'code': c.strip(), 'name': c.strip()} for c in args.codes.split(',')]
    else:
        portfolio = PORTFOLIO_DEFAULT

    print("v6增强分析 " + str(len(portfolio)) + " 只基金...", file=sys.stderr)

    # 市场情绪（只查一次）
    north_flow = get_north_flow()
    print("北向资金: " + north_flow.get('trend', 'unknown') + " " + str(north_flow.get('today', 0)) + "亿", file=sys.stderr)

    results = [analyze_single(h['code'], h['name'], args.rank_period) for h in portfolio]
    # 使用多版本组合优化（含货币基金约束）
    money_ratio = 0.10  # 默认10%货币基金
    if hasattr(args, 'money_fund'):
        try:
            money_ratio = float(args.money_fund) / 100 if args.money_fund else 0.10
        except:
            money_ratio = 0.10
    # 构建含货币基金的portfolio
    money_portfolio = list(portfolio)
    if not any('货币' in str(h) or h.get('code') == '003538' for h in money_portfolio):
        money_portfolio.append({'code': '003538', 'name': '招商招利宝货币B', 'is_money': True})
    money_results = [analyze_single(h['code'], h['name'], args.rank_period) if h.get('code') != '003538'
                     else {'code': '003538', 'name': '招商招利宝货币B', 'fund_type': 'money',
                           'metrics': {'annualized': 1.65, 'volatility': 0.1},
                           'today_change': 0, 'rank': {}, 'fee': {}, 'net_annualized': 1.65, 'score': 60, 'label': '建议持有'}
                     for h in money_portfolio]
    opt = optimize_portfolio_multi(money_results, money_fund_ratio=money_ratio)
    print(generate_report(results, opt, north_flow))

if __name__ == '__main__':
    main()
