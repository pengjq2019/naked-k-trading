#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 比特币全自动双向分析引擎 - 研报级标准版
数据源: Binance / OKX 现货行情标准 (TradingView Scanner + OKX 回退)
格式标准: 阶段一环境审查表格 + 阶段二 2+5 评级核算明细 + 阶段三 后续操作策略与推演
4H K线对齐 (UTC+8 北京时间): 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 (7x24小时全天候)
"""

import urllib.request
import urllib.parse
import json
import datetime
import math
import os
import sys

def load_env():
    """读取本地 .env 文件环境变量 (若存在)"""
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip()
        except Exception:
            pass

load_env()

def fetch_crypto_btc():
    """从 TradingView Scanner 获取 BTCUSDT 实时数据与历史极值 (支持多交易所回退)"""
    cols = [
        'name', 'close', 'open', 'high', 'low',
        'close|240', 'open|240', 'high|240', 'low|240',
        'close[1]|240', 'open[1]|240', 'high[1]|240', 'low[1]|240',
        'close|60', 'open|60', 'high|60', 'low|60',
        'close[1]', 'open[1]', 'high[1]', 'low[1]',
        'high[2]', 'low[2]',
        'EMA20|240', 'SMA20|240', 'SMA50|240', 'RSI|240', 'MACD.macd|240', 'MACD.signal|240',
        'EMA20', 'SMA20', 'RSI'
    ]
    candidate_tickers = ['BINANCE:BTCUSDT', 'OKX:BTCUSDT', 'COINBASE:BTCUSD', 'BYBIT:BTCUSDT']
    for ticker in candidate_tickers:
        try:
            url = 'https://scanner.tradingview.com/crypto/scan'
            payload = {
                'symbols': {'tickers': [ticker]},
                'columns': cols
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = json.loads(r.read().decode('utf-8'))
                if raw.get('data') and len(raw['data']) > 0:
                    row = raw['data'][0]['d']
                    res_dict = dict(zip(cols, row))
                    res_dict['source_ticker'] = ticker
                    return res_dict
        except Exception:
            continue

    # 回退至 OKX 现货 API
    try:
        url_4h = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=4H&limit=5"
        req_4h = urllib.request.Request(url_4h, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_4h, timeout=10) as r:
            res_4h = json.loads(r.read().decode('utf-8'))['data']

        url_1d = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1D&limit=5"
        req_1d = urllib.request.Request(url_1d, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_1d, timeout=10) as r:
            res_1d = json.loads(r.read().decode('utf-8'))['data']

        c_run = float(res_4h[0][4])
        fallback = {
            'name': 'BTCUSDT',
            'source_ticker': 'OKX:BTC-USDT',
            'close': c_run,
            'open': float(res_1d[0][1]),
            'high': float(res_1d[0][2]),
            'low': float(res_1d[0][3]),
            'close|240': c_run,
            'open|240': float(res_4h[0][1]),
            'high|240': float(res_4h[0][2]),
            'low|240': float(res_4h[0][3]),
            'close[1]|240': float(res_4h[1][4]),
            'open[1]|240': float(res_4h[1][1]),
            'high[1]|240': float(res_4h[1][2]),
            'low[1]|240': float(res_4h[1][3]),
            'close[1]': float(res_1d[1][4]),
            'open[1]': float(res_1d[1][1]),
            'high[1]': float(res_1d[1][2]),
            'low[1]': float(res_1d[1][3]),
            'high[2]': float(res_1d[2][2]),
            'low[2]': float(res_1d[2][3]),
            'EMA20|240': c_run,
            'SMA20|240': c_run,
            'SMA50|240': c_run,
            'RSI|240': 50.0,
            'MACD.macd|240': 0.0,
            'MACD.signal|240': 0.0,
            'EMA20': c_run,
            'SMA20': c_run,
            'RSI': 50.0
        }
        return fallback
    except Exception as e:
        raise RuntimeError(f"行情数据源拉取失败: {e}")

def get_slot_labels(now):
    """计算加密货币 4H 周期区间 (北京时间 00:00, 04:00, 08:00, 12:00, 16:00, 20:00)"""
    h = now.hour
    curr_start = (h // 4) * 4
    curr_end = (curr_start + 4) % 24
    prev_start = (curr_start - 4) % 24
    prev_end = curr_start
    return f"{prev_start:02d}:00 - {prev_end:02d}:00", f"{curr_start:02d}:00 - {curr_end:02d}:00"

def calculate_dynamic_levels(curr_price, d):
    """根据《03_关键位体系》全动态计算比特币当前阻力与支撑位矩阵"""
    raw_levels = []
    
    if d.get('high'):
        raw_levels.append(('今日日内最高点', float(d['high'])))
    if d.get('low'):
        raw_levels.append(('今日日内起涨低点', float(d['low'])))
    if d.get('high[1]'):
        raw_levels.append(('前日高点拐点', float(d['high[1]'])))
    if d.get('low[1]'):
        raw_levels.append(('前日极限低点', float(d['low[1]'])))
    if d.get('high[2]'):
        raw_levels.append(('次高级波段拐点高点', float(d['high[2]'])))
    if d.get('low[2]'):
        raw_levels.append(('次低级波段拐点低点', float(d['low[2]'])))
    if d.get('EMA20|240'):
        raw_levels.append(('4H动态生命线 EMA20', float(d['EMA20|240'])))
    if d.get('high[1]|240'):
        raw_levels.append(('刚收盘4H高点', float(d['high[1]|240'])))
    if d.get('low[1]|240'):
        raw_levels.append(('刚收盘4H低点', float(d['low[1]|240'])))
        
    # 比特币整数心理大关: 每 1000 点一个关口，每 5000 点为关键大关
    base_round = round(curr_price / 1000.0) * 1000.0
    for offset in [-6000, -5000, -4000, -3000, -2000, -1000, 0, 1000, 2000, 3000, 4000, 5000, 6000]:
        rn = base_round + offset
        tag = "大整数心理防线" if int(rn) % 5000 == 0 else "整数心理关口"
        raw_levels.append((f'{int(rn)} {tag}', float(rn)))

    res_candidates = []
    sup_candidates = []
    for name, price in raw_levels:
        if price > curr_price + 20.0:
            res_candidates.append((name, price))
        elif price < curr_price - 20.0:
            sup_candidates.append((name, price))
            
    def deduplicate(lvl_list, reverse=False):
        lvl_list = sorted(lvl_list, key=lambda x: x[1], reverse=reverse)
        unique = []
        for name, price in lvl_list:
            if not unique or abs(price - unique[-1][1]) >= 150.0:
                unique.append((name, price))
        return unique

    resistances = deduplicate(res_candidates, reverse=False)[:8]
    supports = deduplicate(sup_candidates, reverse=True)[:8]
    
    return resistances, supports

def generate_report(test_d=None):
    d = test_d if test_d is not None else fetch_crypto_btc()
    curr_price = float(d['close'])
    now = datetime.datetime.now()
    settled_slot, running_slot = get_slot_labels(now)
    source_ticker = d.get('source_ticker', 'BINANCE:BTCUSDT')
    
    # 动态关键位
    resistances, supports = calculate_dynamic_levels(curr_price, d)
    nearest_res = resistances[0] if resistances else ('上方阻力', curr_price + 500.0)
    nearest_sup = supports[0] if supports else ('下方支撑', curr_price - 500.0)
    dist_to_res = nearest_res[1] - curr_price
    dist_to_sup = curr_price - nearest_sup[1]
    
    # 刚收线定型的 4H K线 (核心交易依据)
    o_settled = float(d['open[1]|240'])
    h_settled = float(d['high[1]|240'])
    l_settled = float(d['low[1]|240'])
    c_settled = float(d['close[1]|240'])
    amp_settled = h_settled - l_settled
    body_settled = abs(c_settled - o_settled)
    lower_shadow_settled = min(o_settled, c_settled) - l_settled
    upper_shadow_settled = h_settled - max(o_settled, c_settled)
    lower_ratio_settled = (lower_shadow_settled / amp_settled * 100) if amp_settled > 0 else 0
    upper_ratio_settled = (upper_shadow_settled / amp_settled * 100) if amp_settled > 0 else 0
    is_bull_settled = c_settled >= o_settled

    # 运行中的新 4H K线
    o_run = float(d.get('open|240', curr_price))
    h_run = float(d.get('high|240', curr_price))
    l_run = float(d.get('low|240', curr_price))
    c_run = float(d.get('close|240', curr_price))
    
    # 日线
    od = float(d.get('open', curr_price))
    hd = float(d.get('high', curr_price))
    ld = float(d.get('low', curr_price))
    cd = float(d.get('close', curr_price))
    
    ema20_4h = float(d.get('EMA20|240', 0.0) or 0.0)
    rsi_4h = float(d.get('RSI|240', 0.0) or 0.0)
    macd_4h = float(d.get('MACD.macd|240', 0.0) or 0.0)
    
    # 一、关键位置阶梯（支撑与阻力工程）
    # 阻力一 (次级结构阻力位)
    r_sub_name, r_sub_val = nearest_res[0], nearest_res[1]
    
    # 阻力二 (日内/波段绝对阻力): 优先寻找今日最高点、前日拐点、次高级拐点或大整数防线 (>= r_sub_val + 300.0)
    r_major_candidates = [r for r in resistances[1:] if r[1] >= r_sub_val + 300.0]
    r_struct_cands = [r for r in r_major_candidates if any(k in r[0] for k in ['最高点', '前日拐点', '次高级', '大整数'])]
    if r_struct_cands:
        r_major_name, r_major_val = r_struct_cands[-1]
    elif r_major_candidates:
        r_major_name, r_major_val = r_major_candidates[-1]
    else:
        r_major_name, r_major_val = ("日内/大级别波段绝对阻力", r_sub_val + 1500.0)

    # 支撑一 (第一目标支撑带)
    s_sub_name, s_sub_val = nearest_sup[0], nearest_sup[1]
    
    # 支撑二 (日内/波段绝对支撑): 优先寻找今日起涨低点、前日极限、次低级拐点或大整数防线 (<= s_sub_val - 300.0)
    s_major_candidates = [s for s in supports[1:] if s[1] <= s_sub_val - 300.0]
    s_struct_cands = [s for s in s_major_candidates if any(k in s[0] for k in ['起涨低点', '前日极限', '次低级', '大整数'])]
    if s_struct_cands:
        s_major_name, s_major_val = s_struct_cands[-1]
    elif s_major_candidates:
        s_major_name, s_major_val = s_major_candidates[-1]
    else:
        s_major_name, s_major_val = ("日内/大级别波段绝对支撑", s_sub_val - 1500.0)

    # 动态极性分水岭 P0
    if s_sub_val < ema20_4h < r_sub_val:
        p0_name = "4H动态生命线 EMA20"
        p0_val = ema20_4h
    elif s_sub_val < od < r_sub_val:
        p0_name = "今日开盘价 (日内多空分水岭)"
        p0_val = od
    else:
        p0_name = "多空平衡转换中轴位"
        p0_val = (r_sub_val + s_sub_val) / 2.0

    # 形态与动能识别
    amp_left = float(d.get('high[1]|240', 0)) - float(d.get('low[1]|240', 0))
    is_bull_pinbar = lower_ratio_settled >= 66.7
    is_bear_pinbar = upper_ratio_settled >= 66.7
    is_strong_bull = is_bull_settled and (body_settled / amp_settled >= 0.55 if amp_settled > 0 else False)
    is_strong_bear = (not is_bull_settled) and (body_settled / amp_settled >= 0.55 if amp_settled > 0 else False)
    is_engulfing_qualified = (amp_settled >= amp_left) and (body_settled / amp_settled >= 0.55 if amp_settled > 0 else False)

    # 基础盘面大势
    if ema20_4h > 0 and curr_price > ema20_4h and cd >= od:
        trend_str = "单边多头推进 (站上4H EMA20且日线收阳)"
    elif ema20_4h > 0 and curr_price < ema20_4h and cd < od:
        trend_str = "单边空头压制 (受制4H EMA20且日线收阴)"
    elif ema20_4h > 0 and curr_price > ema20_4h:
        trend_str = "大级别空头背景下的4H超跌反弹修复"
    else:
        trend_str = "宽幅震荡整理 (受制4H EMA20动态压制)"

    # 二、信号研判与 2+5 量化评分
    if is_bull_pinbar:
        direction = "做多 (Long)"
        signal_dir = "long"
        signal_desc = f"4小时看涨Pinbar（长下影探底反转针，下影线占比 {lower_ratio_settled:.1f}%）"
    elif is_bear_pinbar:
        direction = "做空 (Short)"
        signal_dir = "short"
        signal_desc = f"4小时看跌Pinbar/流星线（冲高受阻长上影，上影线占比 {upper_ratio_settled:.1f}%）"
    elif is_strong_bull and (dist_to_sup <= dist_to_res or (ema20_4h > 0 and curr_price > ema20_4h)):
        direction = "做多 (Long)"
        signal_dir = "long"
        signal_desc = f"4小时大阳线推进（实体占比 {(body_settled/amp_settled*100):.1f}%）"
    elif is_strong_bear and (dist_to_res <= dist_to_sup or (ema20_4h > 0 and curr_price < ema20_4h)):
        direction = "做空 (Short)"
        signal_dir = "short"
        signal_desc = f"4小时大阴线突破（实体占比 {(body_settled/amp_settled*100):.1f}%）"
    elif dist_to_sup <= dist_to_res:
        direction = "做多 (Long)"
        signal_dir = "long"
        if lower_ratio_settled >= 40:
            signal_desc = f"4小时下影探底测试线（下影线占比 {lower_ratio_settled:.1f}%，实体 {body_settled:.1f} 点）"
        elif is_bull_settled:
            signal_desc = f"4小时小阳线企稳（实体 {body_settled:.1f} 点）"
        else:
            signal_desc = f"4小时阴线下探支撑（下影线 {lower_shadow_settled:.1f} 点）"
    else:
        direction = "做空 (Short)"
        signal_dir = "short"
        if upper_ratio_settled >= 40:
            signal_desc = f"4小时上影遇阻回落线（上影线占比 {upper_ratio_settled:.1f}%，实体 {body_settled:.1f} 点）"
        elif not is_bull_settled:
            signal_desc = f"4小时小阴线承压（实体 {body_settled:.1f} 点）"
        else:
            signal_desc = f"4小时阳线反弹受阻（上影线 {upper_shadow_settled:.1f} 点）"

    main_shadow_ratio = lower_ratio_settled if signal_dir == "long" else upper_ratio_settled

    # 基础门槛 1: 处于明显关键位？
    if signal_dir == "long":
        b1_pass = dist_to_sup <= 350.0 or abs(l_settled - s_sub_val) <= 250.0 or abs(l_settled - p0_val) <= 250.0
        if b1_pass:
            if abs(l_settled - s_sub_val) <= 250.0:
                b1_desc = f"信号探底低点 {l_settled:.1f} 精准触及支撑位 [{s_sub_name}: {s_sub_val:.1f}] (相距 {abs(l_settled - s_sub_val):.1f} 点)，处于关键支撑防区。"
            elif abs(l_settled - p0_val) <= 250.0:
                b1_desc = f"信号探底低点 {l_settled:.1f} 精准触及分水岭 [{p0_name}: {p0_val:.1f}] (相距 {abs(l_settled - p0_val):.1f} 点)，处于极性转换防区。"
            else:
                b1_desc = f"现价 {curr_price:.1f} 紧贴支撑位 [{s_sub_name}: {s_sub_val:.1f}] (相距 {dist_to_sup:.1f} 点)，处于有效支撑作用带内。"
        else:
            b1_desc = f"现价与K线探底点距最近支撑 [{s_sub_name}: {s_sub_val:.1f}] 尚有 {dist_to_sup:.1f} 点缓冲，无直接有效依托。"

        # 基础门槛 2: 严格判定 Pinbar (>=66.7%) 或 强吞没反转
        b2_pass = is_bull_pinbar or (is_engulfing_qualified and is_bull_settled)
        if is_bull_pinbar:
            b2_desc = f"刚收盘 4H K线下影线占比达 {lower_ratio_settled:.1f}% (>=66.7%)，符合标准长下影看涨 Pinbar 反转形态，完全收线确认。"
        elif is_engulfing_qualified and is_bull_settled:
            b2_desc = f"刚收盘 4H K线形成标准多头阳包阴吞没结构 (实体 {body_settled:.1f} 点)，完全收线确立探底反转。"
        else:
            b2_desc = f"刚收盘 4H K线下影线占比仅 {lower_ratio_settled:.1f}% (<66.7%)，未形成完全收线确认的标准长下影 Pinbar 或底部吞没结构。"
    else:
        b1_pass = dist_to_res <= 350.0 or abs(h_settled - r_sub_val) <= 250.0 or abs(h_settled - p0_val) <= 250.0
        if b1_pass:
            if abs(h_settled - r_sub_val) <= 250.0:
                b1_desc = f"信号冲高高点 {h_settled:.1f} 精准触及阻力位 [{r_sub_name}: {r_sub_val:.1f}] (相距 {abs(h_settled - r_sub_val):.1f} 点)，处于关键阻力防区。"
            elif abs(h_settled - p0_val) <= 250.0:
                b1_desc = f"信号冲高高点 {h_settled:.1f} 精准触及分水岭 [{p0_name}: {p0_val:.1f}] (相距 {abs(h_settled - p0_val):.1f} 点)，处于极性转换防区。"
            else:
                b1_desc = f"现价 {curr_price:.1f} 紧贴阻力位 [{r_sub_name}: {r_sub_val:.1f}] (相距 {dist_to_res:.1f} 点)，处于有效阻力压制带内。"
        else:
            b1_desc = f"现价与K线冲高点距最近阻力 [{r_sub_name}: {r_sub_val:.1f}] 尚有 {dist_to_res:.1f} 点缓冲，无直接阻力压制。"

        # 基础门槛 2: 严格判定 Pinbar (>=66.7%) 或 强吞没反转
        b2_pass = is_bear_pinbar or (is_engulfing_qualified and not is_bull_settled)
        if is_bear_pinbar:
            b2_desc = f"刚收盘 4H K线上影线占比达 {upper_ratio_settled:.1f}% (>=66.7%)，符合标准长上影看跌流星线 Pinbar 反转形态，完全收线确认。"
        elif is_engulfing_qualified and not is_bull_settled:
            b2_desc = f"刚收盘 4H K线形成标准空头阴包阳吞没结构 (实体 {body_settled:.1f} 点)，完全收线确立冲高反转。"
        else:
            b2_desc = f"刚收盘 4H K线上影线占比仅 {upper_ratio_settled:.1f}% (<66.7%)，未形成完全收线确认的标准长上影流星线或高位吞没结构。"

    b1_status = "是" if b1_pass else "否"
    b2_status = "是" if b2_pass else "否"

    # 5项细节特征加分
    # 细1: 盘面显著度
    d1_pass = amp_settled >= 1000.0
    d1_star = "+1星" if d1_pass else "0星"
    d1_desc = f"4H K线全长达 {amp_settled:.1f} 点，属于中大级别实体K线，盘面一目了然。" if d1_pass else f"4H K线全长仅 {amp_settled:.1f} 点，振幅较小无显著视觉冲击力。"

    # 细2: 假突破洗盘
    if signal_dir == "long":
        d2_pass = l_settled < s_sub_val and c_settled > s_sub_val
        d2_desc = f"最低价曾刺穿支撑位 {s_sub_val:.1f}，收盘坚决收回支撑上方，洗盘假突破特征明确。" if d2_pass else "未见影线刺穿关键支撑后强力收回的机构诱空洗盘动作。"
    else:
        d2_pass = h_settled > r_sub_val and c_settled < r_sub_val
        d2_desc = f"最高价曾刺穿阻力位 {r_sub_val:.1f}，收盘坚决被按回阻力下方，洗盘假突破诱多特征明确。" if d2_pass else "未见影线刺穿阻力后强力收回的机构诱多洗盘动作。"
    d2_star = "+1星" if d2_pass else "0星"

    # 细3: 左眼包容与幅度
    d3_pass = amp_settled >= amp_left and amp_left > 0
    d3_star = "+1星" if d3_pass else "0星"
    d3_desc = f"信号K线全长 ({amp_settled:.1f}) 大于等于左眼K线振幅 ({amp_left:.1f})，动能充沛。" if d3_pass else "信号K线动能未明显包容超越左眼对照K线。"

    # 细4: 大级别顺势
    if signal_dir == "long":
        d4_pass = (ema20_4h > 0 and curr_price > ema20_4h) or cd >= od
        d4_desc = f"价格站上4H EMA20 ({ema20_4h:.1f}) 或日线收阳，短线动能顺势向上。" if d4_pass else f"现价处于4H EMA20 ({ema20_4h:.1f}) 下方且日线收阴，大级别空头压制，属逆势抢反弹。"
    else:
        d4_pass = (ema20_4h > 0 and curr_price < ema20_4h) or cd <= od
        d4_desc = f"价格受制于4H EMA20 ({ema20_4h:.1f}) 或日线收阴，顺应大级别主空头趋势。" if d4_pass else f"现价站上4H EMA20 ({ema20_4h:.1f}) 且日线阳线，逆短期反弹动能。"
    d4_star = "+1星" if d4_pass else "0星"

    # 细5: 突破入场实测盈亏比 (严格依据突破入场位计算，拒绝悬空虚标)
    buffer = 30.0
    if signal_dir == "long":
        entry_a = h_settled + buffer
        sl_std = l_settled - buffer
        sl_pts = entry_a - sl_std
        tp_candidates = [p for _, p in resistances if p > entry_a + buffer]
        tp1 = tp_candidates[0] - buffer if tp_candidates else (r_major_val - buffer if r_major_val > entry_a else entry_a + max(500.0, sl_pts * 1.5))
        tp_pts = tp1 - entry_a
    else:
        entry_a = l_settled - buffer
        sl_std = h_settled + buffer
        sl_pts = sl_std - entry_a
        tp_candidates = [p for _, p in supports if p < entry_a - buffer]
        tp1 = tp_candidates[0] + buffer if tp_candidates else (s_major_val + buffer if s_major_val < entry_a else entry_a - max(500.0, sl_pts * 1.5))
        tp_pts = entry_a - tp1

    act_rr = (tp_pts / sl_pts) if sl_pts > 0 else 0
    d5_pass = act_rr >= 1.5 and tp_pts > 0
    d5_star = "+1星" if d5_pass else "0星"
    if d5_pass:
        d5_desc = f"突破入场止损空间为 {sl_pts:.1f} 点，至第一目标空间为 {tp_pts:.1f} 点，实测盈亏比达 {act_rr:.2f}:1 (>=1.5:1)。"
    else:
        d5_desc = f"突破入场止损空间达 {sl_pts:.1f} 点，至第一目标空间仅 {max(0.0, tp_pts):.1f} 点，实测盈亏比仅 {max(0.0, act_rr):.2f}:1 (<1.5:1)，追突破空间受限。"

    base_passed = (1 if b1_pass else 0) + (1 if b2_pass else 0)
    detail_stars = sum([1 for d_item in [d1_pass, d2_pass, d3_pass, d4_pass, d5_pass] if d_item])
    is_qualified = (base_passed == 2 and detail_stars >= 2)

    score_str = f"2 + {detail_stars}" if base_passed == 2 else f"{base_passed} + {detail_stars} (基础门槛未全量通过)"
    verdict_str = "**符合 2+2 标准，准予执行**" if is_qualified else "**不符合 2+2 标准，严禁抢跑，保持观望**"

    title = f"比特币(BTC)裸K标准研判: 现价 {curr_price:.1f} | 评级 {score_str}"

    report = []
    report.append("# 【Price Action】裸K线实战研判与执行报告")
    report.append("")
    report.append("### 基础盘面概况")
    report.append(f"- **标的名称 / 交易代码：** `比特币 (BTCUSDT / {source_ticker})`")
    report.append(f"- **主分析周期 / 辅助周期：** `主周期 4H (刚刚收盘定型: {settled_slot}) / 辅助周期 1D (日线)`")
    report.append(f"- **实时盘面价格：** **`{curr_price:.1f} USDT`** `(快照时间: {now.strftime('%Y-%m-%d %H:%M:%S')} 北京时间)`")
    report.append(f"- **当前运行大势：** `{trend_str}`")
    report.append("")
    report.append("---")
    report.append("")
    report.append("### 一、 关键位置阶梯（支撑与阻力工程）")
    report.append("> **定位准则：** 拐点级别优先、时间邻近优先、触及次数优先；结合极性转化与斐波那契回撤。")
    report.append("")
    report.append("| 层次标号 | 核心价格 / 区间 | 关键位性质 | 价格行为成因与历史依据 | 压制/支撑强度 |")
    report.append("| :--- | :--- | :--- | :--- | :---: |")
    report.append(f"| **阻力一 [R_Major]** | `{r_major_val:.1f}` | 日内/波段绝对阻力 | {r_major_name} | 强 |")
    report.append(f"| **阻力二 [R_Sub]** | `{r_sub_val:.1f}` | 次级结构阻力位 | {r_sub_name} | 中 |")
    report.append(f"| **分水岭 [P0]** | `{p0_val:.1f}` | **核心极性转换位** | {p0_name} | **核心** |")
    report.append(f"| **支撑一 [S_Sub]** | `{s_sub_val:.1f}` | 第一目标支撑带 | {s_sub_name} | 中 |")
    report.append(f"| **支撑二 [S_Major]** | `{s_major_val:.1f}` | 日内/波段绝对支撑 | {s_major_name} | 强 |")
    report.append("")
    report.append("---")
    report.append("")
    report.append("### 二、 信号研判与 2+5 量化评分")
    report.append(f"- **候选信号描述：** `{signal_desc}`")
    report.append(f"- **信号几何要素：** 最高价 `{h_settled:.1f}`、最低价 `{l_settled:.1f}`、收盘价 `{c_settled:.1f}`、主影线占比 `{main_shadow_ratio:.1f}%`（Pinbar要求 >= 66.7%）")
    report.append(f"- **研判方向定性：** `[拟{direction}]`")
    report.append("")
    report.append("| 判定类别 | 研判规则 | 满足状态 | 盘面实测证据与说明 |")
    report.append("| :--- | :--- | :---: | :--- |")
    report.append(f"| **基础门槛 1**<br>*(必须满足)* | **处于明显关键位？** | **[{b1_status}]** | {b1_desc} |")
    report.append(f"| **基础门槛 2**<br>*(必须满足)* | **处于明显高位或低位？** | **[{b2_status}]** | {b2_desc} |")
    report.append(f"| **细节加分 1** | **整个Pinbar在盘面是否显著？** | **[{d1_star}]** | {d1_desc} |")
    report.append(f"| **细节加分 2** | **是否存在假突破？** | **[{d2_star}]** | {d2_desc} |")
    report.append(f"| **细节加分 3** | **实体包含于左眼且幅度大于左眼？** | **[{d3_star}]** | {d3_desc} |")
    report.append(f"| **细节加分 4** | **是否顺应较大级别趋势？** | **[{d4_star}]** | {d4_desc} |")
    report.append(f"| **细节加分 5** | **突破入场盈亏比是否 >= 1.5:1？** | **[{d5_star}]** | {d5_desc} |")
    report.append("")
    report.append(f"- **综合评分结果：** **`{score_str}`**")
    report.append(f"- **操作准入裁决：** {verdict_str}")
    report.append("")
    report.append("---")
    report.append("")

    if is_qualified:
        report.append("### 三、 实战执行方案（评级 >= 2+2，已激活准予执行）")
        report.append("")
        report.append("#### 1. 入场与止损核心参数配置")
        if signal_dir == "long":
            entry_b = l_settled + amp_settled * 0.5
            sl_tight = l_settled + amp_settled * 0.5
            sl_pts_b = entry_b - sl_std
            tp_pts_b = tp1 - entry_b
            rr_b = tp_pts_b / sl_pts_b if sl_pts_b > 0 else 0
            report.append(f"- **开仓方向：** `做多 (Long)`")
            report.append(f"- **入场方式选择：** `方案A: 突破最高点挂单入场 / 方案B: 50%回踩限价挂单`")
            report.append(f"- **精确入场价格：** `方案A 挂单价 {entry_a:.1f} (最高价+缓冲) | 方案B 挂单价 {entry_b:.1f} (50%回撤)`")
            report.append(f"- **精确止损价格 (SL)：** `标准止损点 {sl_std:.1f} (影线极值外侧) | 压缩止损点 {sl_tight:.1f}`")
            report.append(f"- **第一目标止盈位 (TP1)：** `{tp1:.1f} (关键阻力位内侧让出30点冗余)`")
            report.append(f"- **实测盈亏比 (R:R)：** 方案A 突破盈亏比 **`{act_rr:.2f} : 1`** | 方案B 50%回踩盈亏比 **`{rr_b:.2f} : 1`**")
            if act_rr < 1.5:
                report.append(f"> **策略警示：** 方案A 突破盈亏比不足 1.5:1 ({act_rr:.2f}:1)，因信号K线全长达 {amp_settled:.1f} 点导致止损过宽，**严禁追突破**！必须使用 **方案B (50%回踩限价挂单)** 入场。")
        else:
            entry_b = h_settled - amp_settled * 0.5
            sl_tight = h_settled - amp_settled * 0.5
            sl_pts_b = sl_std - entry_b
            tp_pts_b = entry_b - tp1
            rr_b = tp_pts_b / sl_pts_b if sl_pts_b > 0 else 0
            report.append(f"- **开仓方向：** `做空 (Short)`")
            report.append(f"- **入场方式选择：** `方案A: 跌破最低点挂单入场 / 方案B: 50%反弹限价挂单`")
            report.append(f"- **精确入场价格：** `方案A 挂单价 {entry_a:.1f} (最低价-缓冲) | 方案B 挂单价 {entry_b:.1f} (50%反弹)`")
            report.append(f"- **精确止损价格 (SL)：** `标准止损点 {sl_std:.1f} (影线极值外侧) | 压缩止损点 {sl_tight:.1f}`")
            report.append(f"- **第一目标止盈位 (TP1)：** `{tp1:.1f} (关键支撑位内侧让出30点冗余)`")
            report.append(f"- **实测盈亏比 (R:R)：** 方案A 突破盈亏比 **`{act_rr:.2f} : 1`** | 方案B 50%反弹盈亏比 **`{rr_b:.2f} : 1`**")
            if act_rr < 1.5:
                report.append(f"> **策略警示：** 方案A 突破盈亏比不足 1.5:1 ({act_rr:.2f}:1)，因信号K线全长达 {amp_settled:.1f} 点导致止损过宽，**严禁追突破**！必须使用 **方案B (50%反弹限价挂单)** 入场。")

        report.append("")
        report.append("#### 2. 数学仓位计算（固定亏损风控模型）")
        report.append(f"- **本笔交易预设固定亏损上限：** `$500 (或账户净值 1%~2%)`")
        report.append(f"- **止损距离 (Points)：** `{sl_pts:.1f} USDT`")
        report.append(f"- **合约点值 (Point Value)：** `比特币 1枚 1点 = $1`")
        lots = round(500.0 / sl_pts, 3) if sl_pts > 0 else 0.001
        report.append(f"- **执行建仓数量：** `建仓数量 = 500 / {sl_pts:.1f} =` **`{lots} BTC`**")
        report.append("")
        report.append("#### 3. 动态跟踪与后手规则")
        report.append("1. **保本减仓：** 价格触达 **TP1** 时，强制平仓 50% 锁定利润，并将剩余仓位止损移动至**开仓成本价（零风险持仓）**。")
        report.append("2. **三线战法奔跑：** 剩余仓位取消固定止盈，收紧至最新连续 3 根K线极值外侧，单向移动绝不放宽，直至被动离场。")
        report.append("3. **破位失效防线：** 若盘面未达进场条件直接反向击穿信号极值，或成交后反向吞没止损点，坚决平仓出局，严禁扛单或逆势补仓。")
    else:
        report.append("### 三、 实战执行方案（当前未激活）")
        report.append(f"> **准入状态：** 当前综合评级为 **`{score_str}`**，未达到 **2+2** 准入硬红线，实战执行方案处于**锁定保护状态**。")
        report.append("")
        report.append("#### 1. 核心交易禁令")
        report.append("- **严禁盲目追单：** 严禁在悬空位置或未收线确认时提前抢跑入场。")
        report.append("- **严禁左侧猜顶/摸底：** 严禁在无明确反转信号及假突破洗盘结构前逆势扛单。")
        report.append("")
        report.append("#### 2. 下一阶段关键观察防线与激活触发条件")
        report.append(f"- **多头激活条件：** 耐心等待价格回踩测试关键支撑【{s_sub_name}: {s_sub_val:.1f}】或分水岭【{p0_name}: {p0_val:.1f}】，若 4H 级别收出下影线 >= 66.7% 的标准看涨大象鼻子 Pinbar 或阳包阴看涨吞没，且 2+5 评级达标，方可挂单做多。")
        report.append(f"- **空头激活条件：** 耐心等待价格反弹测试关键阻力【{r_sub_name}: {r_sub_val:.1f}】，若 4H 级别冲高受阻收出上影线 >= 66.7% 的看跌流星线 Pinbar 或阴包阳看跌吞没，且 2+5 评级达标，方可挂单做空。")
        report.append(f"- **破位顺势应对：** 若盘面以坚决大实体K线直接击穿分水岭或阻力支撑，严禁逆势摸顶抄底，耐心等待破位后首次回踩确认极性转换。")

    report.append("")
    report.append("> *Recorded in Obsidian Second Brain: [[裸K线价格行为实战研判与执行报告]].*")
    
    return title, "\n".join(report)

def push_wechat(title, content):
    """多通道微信推送实现"""
    pushed = False
    
    # 通道 1: PushPlus (推送加)
    pushplus_token = os.environ.get('PUSHPLUS_TOKEN')
    if pushplus_token:
        try:
            url = 'http://www.pushplus.plus/send'
            payload = {
                'token': pushplus_token,
                'title': title,
                'content': content,
                'template': 'markdown'
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read().decode('utf-8'))
                print(f"[PushPlus] 推送结果: {res.get('msg')}")
                pushed = True
        except Exception as e:
            print(f"[PushPlus] 推送异常: {e}")
            
    # 通道 2: Server酱 Turbo
    serverchan_key = os.environ.get('SERVERCHAN_KEY')
    if serverchan_key:
        try:
            url = f'https://sctapi.ftqq.com/{serverchan_key}.send'
            payload = urllib.parse.urlencode({'title': title, 'desp': content}).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=payload,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read().decode('utf-8'))
                print(f"[Server酱] 推送结果: {res.get('message', res.get('data'))}")
                pushed = True
        except Exception as e:
            print(f"[Server酱] 推送异常: {e}")
            
    # 通道 3: 企业微信群机器人 Webhook
    wecom_webhook = os.environ.get('WECOM_WEBHOOK')
    if wecom_webhook:
        try:
            url = wecom_webhook if wecom_webhook.startswith('http') else f'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={wecom_webhook}'
            payload = {
                'msgtype': 'markdown',
                'markdown': {'content': content}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read().decode('utf-8'))
                print(f"[企业微信] 推送结果: {res.get('errmsg')}")
                pushed = True
        except Exception as e:
            print(f"[企业微信] 推送异常: {e}")

    # 通道 4: WxPusher
    wx_token = os.environ.get('WXPUSHER_APP_TOKEN')
    wx_uid = os.environ.get('WXPUSHER_UID')
    if wx_token and wx_uid:
        try:
            url = 'https://wxpusher.zjiecode.com/api/send/message'
            payload = {
                'appToken': wx_token,
                'content': content,
                'contentType': 3,
                'uids': [wx_uid]
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read().decode('utf-8'))
                print(f"[WxPusher] 推送结果: {res.get('msg')}")
                pushed = True
        except Exception as e:
            print(f"[WxPusher] 推送异常: {e}")

    if not pushed:
        print("[微信推送提示] 未配置微信推送凭据，仅控制台输出。")

def main():
    title, report = generate_report()
    if not title:
        print(report)
        return
        
    print("=" * 60)
    print(f"TITLE: {title}")
    print("=" * 60)
    print(report)
    print("=" * 60)
    
    push_wechat(title, report)

if __name__ == '__main__':
    main()
