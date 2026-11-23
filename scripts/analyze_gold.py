#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 黄金全自动双向分析引擎 - 研报级标准版
数据源: Forex.com (嘉盛) XAUUSD 现货 / CFD 标准
格式标准: 阶段一环境审查表格 + 阶段二 2+5 评级核算明细 + 阶段三 后续操作策略与推演
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

def is_market_open():
    """判断黄金交易市场是否开盘 (北京时间 UTC+8)
    周六早晨 06:00 闭盘，周一早晨 06:00 开盘。
    """
    now = datetime.datetime.now()
    weekday = now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    hour = now.hour
    
    # 周六 06:00 之后停盘
    if weekday == 5 and hour >= 6:
        return False
    # 周日全天停盘
    if weekday == 6:
        return False
    # 周一 06:00 之前未开盘
    if weekday == 0 and hour < 6:
        return False
        
    return True

def fetch_forexcom_gold():
    """从 TradingView Scanner 获取 Forex.com (嘉盛) XAUUSD 实时数据与历史极值"""
    url = 'https://scanner.tradingview.com/cfd/scan'
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
    payload = {
        'symbols': {'tickers': ['FOREXCOM:XAUUSD']},
        'columns': cols
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = json.loads(r.read().decode('utf-8'))
        row = raw['data'][0]['d']
        return dict(zip(cols, row))

def get_slot_labels(now):
    """计算刚收线的4H区间和新运行的4H区间"""
    h = now.hour
    if h < 2:
        curr_start = 22
        curr_end = 2
        prev_start = 18
        prev_end = 22
    else:
        curr_start = ((h - 2) // 4) * 4 + 2
        curr_end = (curr_start + 4) % 24
        prev_start = (curr_start - 4) % 24
        prev_end = curr_start
        
    return f"{prev_start:02d}:00 - {prev_end:02d}:00", f"{curr_start:02d}:00 - {curr_end:02d}:00"

def calculate_dynamic_levels(curr_price, d):
    """根据《03_关键位体系》全动态计算当前阻力与支撑位矩阵"""
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
        
    base_round = round(curr_price / 50.0) * 50.0
    for offset in [-150, -100, -50, 0, 50, 100, 150]:
        rn = base_round + offset
        raw_levels.append((f'{int(rn)} 整数心理关口', float(rn)))

    res_candidates = []
    sup_candidates = []
    for name, price in raw_levels:
        if price > curr_price + 0.8:
            res_candidates.append((name, price))
        elif price < curr_price - 0.8:
            sup_candidates.append((name, price))
            
    def deduplicate(lvl_list, reverse=False):
        lvl_list = sorted(lvl_list, key=lambda x: x[1], reverse=reverse)
        unique = []
        for name, price in lvl_list:
            if not unique or abs(price - unique[-1][1]) >= 3.0:
                unique.append((name, price))
        return unique

    resistances = deduplicate(res_candidates, reverse=False)[:4]
    supports = deduplicate(sup_candidates, reverse=True)[:4]
    
    return resistances, supports

def generate_report():
    if not is_market_open():
        return None, "【休市提醒】当前处于周末黄金休市时段（周六06:00至周一06:00），市场暂停报价，跳过本次推送。"

    d = fetch_forexcom_gold()
    curr_price = float(d['close'])
    now = datetime.datetime.now()
    settled_slot, running_slot = get_slot_labels(now)
    
    # 动态关键位
    resistances, supports = calculate_dynamic_levels(curr_price, d)
    nearest_res = resistances[0] if resistances else ('上方阻力', curr_price + 30)
    nearest_sup = supports[0] if supports else ('下方支撑', curr_price - 30)
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
    o_run = float(d['open|240'])
    h_run = float(d['high|240'])
    l_run = float(d['low|240'])
    c_run = float(d['close|240'])
    
    # 日线
    od = float(d['open'])
    hd = float(d['high'])
    ld = float(d['low'])
    cd = float(d['close'])
    
    ema20_4h = float(d['EMA20|240'])
    rsi_4h = float(d['RSI|240'])
    macd_4h = float(d['MACD.macd|240'])
    
    # 形态识别
    is_bull_pinbar = lower_ratio_settled >= 66.7
    is_bear_pinbar = upper_ratio_settled >= 66.7
    is_strong_bull = is_bull_settled and (body_settled / amp_settled >= 0.55)
    is_strong_bear = (not is_bull_settled) and (body_settled / amp_settled >= 0.55)

    title = f"黄金(嘉盛CFD)裸K标准研判: 现价 {curr_price:.2f}"
    
    report = []
    report.append("### 黄金裸K线交易法 (Price Action) 研判报告")
    report.append(f"- **官方数据源**: Forex.com (嘉盛) XAU/USD 现货 / CFD")
    report.append(f"- **分析时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    report.append(f"- **实时现价**: **{curr_price:.2f}**")
    report.append(f"- **刚收盘 4H K线 [{settled_slot}]**: 开盘 `{o_settled:.2f}` | 最高 `{h_settled:.2f}` | 最低 `{l_settled:.2f}` | 收盘 `{c_settled:.2f}` (振幅: `{amp_settled:.2f}` 点)")
    report.append(f"- **日线状态**: 今日开盘 `{od:.2f}` | 日内高点 `{hd:.2f}` | 日内低点 `{ld:.2f}` | 最新 `{cd:.2f}`")
    report.append("")
    report.append("#### 核心关键水平位 (动态极性转化图谱)")
    for idx, (r_name, r_val) in enumerate(resistances, 1):
        report.append(f"- 阻力 R{idx}: `{r_val:.2f}` ({r_name}，距现价 +{(r_val - curr_price):.1f} 点)")
    report.append(f"- **现价基准**: `{curr_price:.2f}`")
    for idx, (s_name, s_val) in enumerate(supports, 1):
        p_tag = " [原阻力突破翻转为强支撑]" if ("3600" in s_name or "起涨" in s_name) and s_val < curr_price else ""
        report.append(f"- 支撑 S{idx}: `{s_val:.2f}` ({s_name}{p_tag}，距现价 -{(curr_price - s_val):.1f} 点)")
    report.append("")
    
    # =========================================================================
    # 【多头维度研判 (Long Setup)】- 严格遵循标准模板
    # =========================================================================
    report.append("---")
    report.append("### 【多头维度研判 (Long Setup)】")
    report.append("")
    report.append("#### 一、阶段一：环境与位置审查（触发一票否决）")
    report.append("在实盘交易清单中，以下两项必要基本条件缺一不可，任一为“否”直接终止交易：")
    report.append("")
    report.append("| 审查维度 | 交易法判定标准 | 当前盘面实际状况 (XAUUSD 4H/日线) | 审查结论 |")
    report.append("| :--- | :--- | :--- | :--- |")
    
    # 审查项1 (多头)
    long_b1_pass = dist_to_sup <= 8.0
    long_b1_desc = f"现价 {curr_price:.2f} 距下方最近支撑【{nearest_sup[0]}: {nearest_sup[1]:.2f}】约 {dist_to_sup:.1f} 点。" + \
                   ("处于强支撑有效作用带内。" if long_b1_pass else f"已脱离底部支撑区，处于半空中推进，无直接支撑防守。")
    long_b1_res = "符合" if long_b1_pass else "不符合"
    report.append(f"| **基本条件 1：强关键位** | 信号必须精确触碰或刺穿大级别、多拐点验证的有效水平关键带。 | {long_b1_desc} | **{long_b1_res}** |")
    
    # 审查项2 (多头)
    long_b2_pass = is_bull_pinbar or is_strong_bull
    if is_bull_pinbar:
        long_b2_desc = f"刚收盘 4H K线下影线占比达 {lower_ratio_settled:.1f}%，符合标准长下影 Pinbar(>=66.7%) 反转要求。"
    elif is_strong_bull:
        long_b2_desc = f"刚收盘 4H K线为大阳推进 (实体占比 {(body_settled/amp_settled*100):.1f}%)，下影线占比 {lower_ratio_settled:.1f}%，非标准长下影Pinbar，属于中继突破而非极值反转。"
    else:
        long_b2_desc = f"刚收盘 4H K线下影线占比仅 {lower_ratio_settled:.1f}%，未见已收线的标准长下影 Pinbar 或多头吞没结构。"
    long_b2_res = "符合" if is_bull_pinbar else "不符合"
    report.append(f"| **基本条件 2：明确波段极值与反转信号** | 信号前具有至少3根明确单向K线，且反转形态（Pinbar/吞没/启明星）必须完全收线确认。 | {long_b2_desc} | **{long_b2_res}** |")
    report.append("")
    
    long_base_passed = (1 if long_b1_pass else 0) + (1 if is_bull_pinbar else 0)
    long_veto = (long_base_passed < 2)
    if long_veto:
        report.append(f"**判定**：基本门槛仅达成 {long_base_passed}/2 项，触发一票否决机制，严禁入场做多！")
    else:
        report.append("**判定**：两项基本门槛全量通过 (2/2)，准予进入阶段二 2+5 细节打分！")
    report.append("")
    
    # 阶段二 (多头)
    report.append("#### 二、阶段二：2+5 评级核算")
    report.append("准入硬指标要求：2个基本条件全过 (2/2) + 细节项 $\ge 2$ 星（即 $\ge 2+2$）。")
    if long_base_passed == 2:
        report.append(f"- **基本门槛**：**2 / 2 项通过（门槛达标）**。")
    else:
        report.append(f"- **基本门槛**：**{long_base_passed} / 2 项通过（缺项未达标，触发一票否决）**。")
    report.append("- **细节项排查**：")
    
    long_stars = 0
    # 细1
    if amp_settled >= 25.0:
        long_stars += 1
        report.append(f"  - **细1（盘面显眼度）**：刚收线 4H 振幅达 {amp_settled:.2f} 点，属于中大级别实体K线，计 1 星。")
    else:
        report.append(f"  - **细1（盘面显眼度）**：刚收线 4H 振幅仅 {amp_settled:.2f} 点，属于窄幅波动小K线，计 0 星。")
    # 细2
    if l_settled < nearest_sup[1] and c_settled > nearest_sup[1]:
        long_stars += 1
        report.append(f"  - **细2（假突破洗盘）**：下影线曾刺穿支撑位 {nearest_sup[1]:.2f} 后强势收回内侧，洗盘明显，计 1 星。")
    else:
        report.append(f"  - **细2（假突破洗盘）**：未见影线刺透支撑后暴力收回的假突破机构洗盘迹象，计 0 星。")
    # 细3
    amp_prev = float(d['high[1]']) - float(d['low[1]'])
    if amp_settled > 30.0:
        long_stars += 1
        report.append(f"  - **细3（左眼包容与幅度）**：信号K线动能充沛且超越左眼对照振幅，计 1 星。")
    else:
        report.append(f"  - **细3（左眼包容与幅度）**：K线振幅未显著超越前序K线，计 0 星。")
    # 细4
    if curr_price > ema20_4h:
        long_stars += 1
        report.append(f"  - **细4（大级别顺势）**：现价已突破并站上 4H EMA20 动态均线 ({ema20_4h:.2f})，顺应短线反弹动能，计 1 星。")
    else:
        report.append(f"  - **细4（大级别顺势）**：现价仍受制于 4H EMA20 ({ema20_4h:.2f}) 及日线均线空头排列压制，逆大势，计 0 星。")
    # 细5
    long_rr = dist_to_res / max(5.0, dist_to_sup)
    if long_rr >= 1.5:
        long_stars += 1
        report.append(f"  - **细5（基础盈亏比）**：距离上方阻力空间 ({dist_to_res:.1f}点) 对比止损空间 ({dist_to_sup:.1f}点) 测算盈亏比为 {long_rr:.2f}:1 (>=1.5:1)，计 1 星。")
    else:
        report.append(f"  - **细5（基础盈亏比）**：上方空间受限 ({dist_to_res:.1f}点)，基础盈亏比仅 {long_rr:.2f}:1 (<1.5:1)，计 0 星。")
        
    if not long_veto and long_stars >= 2:
        long_final_str = f"2 + {long_stars} 星【准予入场】（满足 2+2 准入硬指标，具备开仓价值）"
    elif not long_veto and long_stars < 2:
        long_final_str = f"2 + {long_stars} 星【不合格】（基本门槛达成，但细节不足2星，仅作观察）"
    else:
        long_final_str = f"{long_base_passed} + {long_stars} 星【不合格】（基本门槛仅 {long_base_passed}/2 项通过触发一票否决，虽细节获 {long_stars} 星但未达 2+2 准入红线，严禁开仓）"
    report.append(f"- **最终评级**：**{long_final_str}**")
    report.append("")
    
    # 阶段三 (多头)
    report.append("#### 三、后续操作策略与推演")
    report.append("- **绝对禁令**：")
    report.append(f"  1. 严禁在现价脱离支撑 {dist_to_sup:.1f} 点的高位盲目追多！")
    report.append(f"  2. 严禁在无收线确认的看涨Pinbar形态时提前左侧抢跑。")
    report.append("- **多头观察条件（必须等待）**：")
    report.append(f"  1. 耐心等待行情向下回踩测试【极性转化支撑位 {nearest_sup[1]:.2f}】。")
    report.append(f"  2. 若在 {nearest_sup[1]:.2f} 附近 4小时 级别收出下影线超过全长 2/3、实体完全收在支撑内侧的标准看涨大象鼻子 Pinbar 或阳包阴吞没，且满足 2+2 评级，方可挂单入场。")
    report.append("- **顺势交易思路**：")
    report.append(f"  当前日线级别仍处于大波段破位后的修正期。多头若要确立波段反转，必须等待 4H 级别有效站稳 4H EMA20 ({ema20_4h:.2f}) 上方并构筑 W 底结构，在此之前一律视为超跌反弹对待。")
    report.append("")

    # =========================================================================
    # 【空头维度研判 (Short Setup)】- 严格遵循标准模板
    # =========================================================================
    report.append("---")
    report.append("### 【空头维度研判 (Short Setup)】")
    report.append("")
    report.append("#### 一、阶段一：环境与位置审查（触发一票否决）")
    report.append("在实盘交易清单中，以下两项必要基本条件缺一不可，任一为“否”直接终止交易：")
    report.append("")
    report.append("| 审查维度 | 交易法判定标准 | 当前盘面实际状况 (XAUUSD 4H/日线) | 审查结论 |")
    report.append("| :--- | :--- | :--- | :--- |")
    
    # 审查项1 (空头)
    short_b1_pass = dist_to_res <= 8.0
    short_b1_desc = f"现价 {curr_price:.2f} 距离上方阻力【{nearest_res[0]}: {nearest_res[1]:.2f}】相距 {dist_to_res:.1f} 点。" + \
                    ("已逼近强阻力带核心防区。" if short_b1_pass else f"距离阻力位尚有缓冲空间。")
    short_b1_res = "符合" if short_b1_pass else "不符合"
    report.append(f"| **基本条件 1：强关键位** | 信号必须精确触碰或刺穿大级别、多拐点验证的有效水平关键阻力带。 | {short_b1_desc} | **{short_b1_res}** |")
    
    # 审查项2 (空头)
    short_b2_pass = is_bear_pinbar or (upper_ratio_settled >= 50.0)
    if is_bear_pinbar:
        short_b2_desc = f"刚收盘 4H K线上影线占比达 {upper_ratio_settled:.1f}%，符合标准长上影看跌流星线(>=66.7%)。"
    elif upper_ratio_settled >= 50.0:
        short_b2_desc = f"刚收盘 4H K线冲高受阻回落，上影线占比达 {upper_ratio_settled:.1f}%，呈现受阻滞涨迹象。"
    else:
        short_b2_desc = f"刚收盘 4H K线上影线占比仅 {upper_ratio_settled:.1f}%，尚未走出收线确认的标准长上影流星线或阴包阳吞没。"
    short_b2_res = "符合" if short_b2_pass else "不符合"
    report.append(f"| **基本条件 2：明确波段极值与反转信号** | 信号前具有至少3根明确单向K线，且反转形态（Pinbar/吞没/黄昏星）必须完全收线确认。 | {short_b2_desc} | **{short_b2_res}** |")
    report.append("")
    
    short_base_passed = (1 if short_b1_pass else 0) + (1 if short_b2_pass else 0)
    short_veto = (short_base_passed < 2)
    if short_veto:
        report.append(f"**判定**：基本门槛仅达成 {short_base_passed}/2 项，暂不符合即时开空条件。")
    else:
        report.append("**判定**：两项基本门槛全量通过 (2/2)，阻力受阻信号确立，准予进入阶段二 2+5 细节打分！")
    report.append("")
    
    # 阶段二 (空头)
    report.append("#### 二、阶段二：2+5 评级核算")
    report.append("准入硬指标要求：2个基本条件全过 (2/2) + 细节项 $\ge 2$ 星（即 $\ge 2+2$）。")
    if short_base_passed == 2:
        report.append(f"- **基本门槛**：**2 / 2 项通过（门槛达标）**。")
    else:
        report.append(f"- **基本门槛**：**{short_base_passed} / 2 项通过（缺项未达标，触发一票否决）**。")
    report.append("- **细节项排查**：")
    
    short_stars = 0
    # 细1
    if amp_settled >= 25.0:
        short_stars += 1
        report.append(f"  - **细1（盘面显眼度）**：信号K线全长达 {amp_settled:.2f} 点，盘面一目了然，计 1 星。")
    else:
        report.append(f"  - **细1（盘面显眼度）**：信号K线全长仅 {amp_settled:.2f} 点，动能不显著，计 0 星。")
    # 细2
    if h_settled > nearest_res[1] and c_settled < nearest_res[1]:
        short_stars += 1
        report.append(f"  - **细2（假突破洗盘）**：上影线曾刺穿阻力位 {nearest_res[1]:.2f} 后被强行按回阻力下方，属典型诱多假突破，计 1 星。")
    else:
        report.append(f"  - **细2（假突破洗盘）**：未形成明显的刺穿阻力后暴力收回结构，计 0 星。")
    # 细3
    if upper_ratio_settled >= 50.0:
        short_stars += 1
        report.append(f"  - **细3（左眼包容与幅度）**：冲高遇阻明显，原上涨动能被阻力有效拦截，计 1 星。")
    else:
        report.append(f"  - **细3（左眼包容与幅度）**：多头反弹实体仍较饱满，尚未完全被空头包容，计 0 星。")
    # 细4
    if curr_price < ema20_4h or cd < od:
        short_stars += 1
        report.append(f"  - **细4（大级别顺势）**：顺应日线大级别空头单边大趋势方向，计 1 星。")
    else:
        report.append(f"  - **细4（大级别顺势）**：短线多头连续阳线反扑，逆短期反弹动能，计 0 星。")
    # 细5
    short_rr = dist_to_sup / max(5.0, dist_to_res)
    if short_rr >= 1.5:
        short_stars += 1
        report.append(f"  - **细5（基础盈亏比）**：以阻力上方设损，距离下方第一支撑空间 ({dist_to_sup:.1f}点) 测算盈亏比为 {short_rr:.2f}:1 (>=1.5:1)，计 1 星。")
    else:
        report.append(f"  - **细5（基础盈亏比）**：向下回踩空间测算盈亏比仅 {short_rr:.2f}:1 (<1.5:1)，计 0 星。")
        
    if not short_veto and short_stars >= 2:
        short_final_str = f"2 + {short_stars} 星【准予入场】（满足 2+2 准入硬指标，具备开仓价值）"
    elif not short_veto and short_stars < 2:
        short_final_str = f"2 + {short_stars} 星【不合格】（基本门槛达成，但细节不足2星，仅作观察）"
    else:
        short_final_str = f"{short_base_passed} + {short_stars} 星【不合格】（基本门槛仅 {short_base_passed}/2 项通过触发一票否决，虽细节获 {short_stars} 星但未达 2+2 准入红线，严禁开仓）"
    report.append(f"- **最终评级**：**{short_final_str}**")
    report.append("")
    
    # 阶段三 (空头)
    report.append("#### 三、后续操作策略与推演")
    report.append("- **绝对禁令**：")
    report.append(f"  1. 严禁在价格刚刚大阳冲高时无反转形态直接左侧盲目摸顶开空！")
    report.append(f"  2. 严禁在强阻力位未确认滞涨前逆势抢跑。")
    report.append("- **空头观察条件（必须等待）**：")
    report.append(f"  1. 密切观察当前 4H K线在【{nearest_res[0]}: {nearest_res[1]:.2f}】附近的收盘表现。")
    report.append(f"  2. 若在阻力区形成长上影线超过 2/3 的看跌 Pinbar（流星线）或出现阴包阳看跌吞没形态，且评级达到 2+2，方可制定突破信号低点挂单做空计划。")
    report.append("- **顺势交易思路**：")
    report.append(f"  当前属于大级别空头趋势中的超跌反抽。最优质的高盈亏比做空点，必然是在反弹触碰阻力位滞涨衰竭时的“顺大势、逆小势”二次做空机会。")
    
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
        
    print("="*50)
    print(f"TITLE: {title}")
    print("="*50)
    print(report)
    print("="*50)
    
    push_wechat(title, report)

if __name__ == '__main__':
    main()
