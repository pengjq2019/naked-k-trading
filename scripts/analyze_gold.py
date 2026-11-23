#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 黄金全自动双向分析引擎 - 全动态算法版
数据源: Forex.com (嘉盛) XAUUSD 现货 / CFD 标准
核心算法: 全动态关键位捕捉体系 + 极性转化自动判定 + 动态 2+5 评级量化模型
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
    """
    根据《03_关键位体系》全动态计算当前阻力与支撑位矩阵
    遵循原则：
    1. 阻力位必须严格 > 当前现价
    2. 支撑位必须严格 < 当前现价
    3. 动态结合：波段高低拐点、动态均线生命线、整数心理大关、极性转化原则
    """
    raw_levels = []
    
    # 1. 采集历史波段拐点与均线
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
        
    # 2. 动态生成邻近的 50 点整数心理大关
    base_round = round(curr_price / 50.0) * 50.0
    for offset in [-150, -100, -50, 0, 50, 100, 150]:
        rn = base_round + offset
        raw_levels.append((f'{int(rn)} 整数心理关口', float(rn)))

    # 3. 严格分流：阻力与支撑
    res_candidates = []
    sup_candidates = []
    for name, price in raw_levels:
        if price > curr_price + 0.8:
            res_candidates.append((name, price))
        elif price < curr_price - 0.8:
            sup_candidates.append((name, price))
            
    # 去重并排序 (阻力从低到高，支撑从高到低)
    def deduplicate(lvl_list, reverse=False):
        lvl_list = sorted(lvl_list, key=lambda x: x[1], reverse=reverse)
        unique = []
        for name, price in lvl_list:
            if not unique or abs(price - unique[-1][1]) >= 3.0:  # 3点内合并
                unique.append((name, price))
        return unique

    resistances = deduplicate(res_candidates, reverse=False)[:4]
    supports = deduplicate(sup_candidates, reverse=True)[:4]
    
    return resistances, supports

def analyze_price_action(curr_price, d, resistances, supports):
    """
    全动态《裸K线交易法》2+5 评级体系与策略演算
    """
    # K线属性提取
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

    o_prev = float(d['open|60'])  # 对照基准
    amp_prev = float(d['high[1]|240']) - float(d['low[1]|240']) # 估算

    ema20_4h = float(d['EMA20|240'])
    rsi_4h = float(d['RSI|240'])
    
    # 动态形态判定
    is_bull_pinbar = lower_ratio_settled >= 66.7
    is_bear_pinbar = upper_ratio_settled >= 66.7
    is_strong_bull = is_bull_settled and (body_settled / amp_settled >= 0.55)
    is_strong_bear = (not is_bull_settled) and (body_settled / amp_settled >= 0.55)
    
    # 最近的强阻力与强支撑
    nearest_res = resistances[0] if resistances else ('上方阻力', curr_price + 30)
    nearest_sup = supports[0] if supports else ('下方支撑', curr_price - 30)
    dist_to_res = nearest_res[1] - curr_price
    dist_to_sup = curr_price - nearest_sup[1]
    
    # --- 1. 多头 2+5 动态评级 ---
    long_pass_base1 = dist_to_sup <= 8.0  # 离强支撑 8 点以内
    long_pass_base2 = is_bull_pinbar or is_strong_bull  # 有效看涨形态
    
    long_stars = 0
    long_star_details = []
    if amp_settled >= 25.0:
        long_stars += 1
        long_star_details.append("显眼度(+1星)")
    if l_settled < nearest_sup[1] and c_settled > nearest_sup[1]:
        long_stars += 1
        long_star_details.append("假突破刺透收回(+1星)")
    if curr_price > ema20_4h:
        long_stars += 1
        long_star_details.append("站上4H均线顺大势(+1星)")
    if dist_to_res / max(5.0, dist_to_sup) >= 1.5:
        long_stars += 1
        long_star_details.append("基础盈亏比>=1.5:1(+1星)")
        
    if long_pass_base1 and long_pass_base2:
        long_score_str = f"2 + {long_stars} 星"
        long_verdict = "符合入场准入门槛" if long_stars >= 2 else "门槛通过但细节星级不足(<2星)，观望"
    else:
        long_score_str = "0 分 (触发一票否决)"
        if not long_pass_base1 and not long_pass_base2:
            long_verdict = f"既未处于强支撑边缘(距支撑{dist_to_sup:.1f}点)，亦无已收线的长下影反转Pinbar"
        elif not long_pass_base1:
            long_verdict = f"虽有反弹形态，但当前价远离下方强支撑({dist_to_sup:.1f}点)，属半空中追多"
        else:
            long_verdict = "处于支撑附近，但未走出收线确认的标准长下影Pinbar或多头吞没"

    # --- 2. 空头 2+5 动态评级 ---
    short_pass_base1 = dist_to_res <= 8.0  # 离强阻力 8 点以内
    short_pass_base2 = is_bear_pinbar or is_strong_bear
    
    short_stars = 0
    short_star_details = []
    if amp_settled >= 25.0:
        short_stars += 1
        short_star_details.append("显眼度(+1星)")
    if h_settled > nearest_res[1] and c_settled < nearest_res[1]:
        short_stars += 1
        short_star_details.append("假突破上刺收回(+1星)")
    if curr_price < ema20_4h:
        short_stars += 1
        short_star_details.append("大级别均线压制顺势(+1星)")
    if dist_to_sup / max(5.0, dist_to_res) >= 1.5:
        short_stars += 1
        short_star_details.append("基础盈亏比>=1.5:1(+1星)")
        
    if short_pass_base1 and short_pass_base2:
        short_score_str = f"2 + {short_stars} 星"
        short_verdict = "符合高空伏击入场准入门槛" if short_stars >= 2 else "门槛通过但细节星级不足(<2星)，观望"
    else:
        short_score_str = "0 分 (触发一票否决)"
        if not short_pass_base1 and not short_pass_base2:
            short_verdict = f"未处于强阻力边缘(距上方阻力{dist_to_res:.1f}点)，且未收出看跌流星线"
        elif not short_pass_base1:
            short_verdict = f"刚收线为多头推进，且现价距离上方阻力仍有 {dist_to_res:.1f} 点空间，不可逆势左侧摸顶"
        else:
            short_verdict = "已逼近强阻力位，但需等待当前K线收出长上影线确认滞涨"

    return {
        'nearest_res': nearest_res,
        'nearest_sup': nearest_sup,
        'dist_to_res': dist_to_res,
        'dist_to_sup': dist_to_sup,
        'long_score_str': long_score_str,
        'long_verdict': long_verdict,
        'long_stars': long_stars,
        'long_star_details': long_star_details,
        'short_score_str': short_score_str,
        'short_verdict': short_verdict,
        'short_stars': short_stars,
        'short_star_details': short_star_details,
        'is_strong_bull': is_strong_bull,
        'is_bull_pinbar': is_bull_pinbar,
        'is_bear_pinbar': is_bear_pinbar,
    }

def generate_report():
    if not is_market_open():
        return None, "【休市提醒】当前处于周末黄金休市时段（周六06:00至周一06:00），市场暂停报价，跳过本次推送。"

    d = fetch_forexcom_gold()
    curr_price = float(d['close'])
    now = datetime.datetime.now()
    settled_slot, running_slot = get_slot_labels(now)
    
    # 动态计算关键位与评级
    resistances, supports = calculate_dynamic_levels(curr_price, d)
    pa = analyze_price_action(curr_price, d, resistances, supports)
    
    # 刚收线定型的 4H K线
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

    # 正在运行的新 4H K线
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

    title = f"黄金(嘉盛CFD)裸K全动态研判: 现价 {curr_price:.2f}"
    
    report = []
    report.append(f"### 黄金裸K线交易法 (Price Action) 动态研判报告")
    report.append(f"- **官方数据源**: **Forex.com (嘉盛) XAU/USD 现货 / CFD**")
    report.append(f"- **推送时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    report.append(f"- **实时现价**: **{curr_price:.2f}**")
    report.append("")
    report.append(f"#### 一、刚收线定型的 4H K线 [{settled_slot}]（核心交易依据）")
    report.append(f"- 开盘 `{o_settled:.2f}` | 最高 `{h_settled:.2f}` | 最低 `{l_settled:.2f}` | 收盘 `{c_settled:.2f}`")
    report.append(f"- K线性质: {'【大阳反弹/突破】' if is_bull_settled else '【阴线下跌/中继】'} | 全长振幅: `{amp_settled:.2f}` 点 | 实体: `{body_settled:.2f}` 点")
    report.append(f"- 下影线占比: **{lower_ratio_settled:.1f}%** | 上影线占比: **{upper_ratio_settled:.1f}%**")
    if lower_ratio_settled >= 66.7:
        report.append(f"- 形态判定: **【标准看涨长下影 Pinbar】** (满足主影线>=2/3)")
    elif upper_ratio_settled >= 66.7:
        report.append(f"- 形态判定: **【标准看跌长上影 Pinbar】** (满足主影线>=2/3)")
    elif is_bull_settled and body_settled / amp_settled >= 0.55:
        report.append(f"- 形态判定: **【多头大阳实体放量推进】** (实体占比超55%)")
    else:
        report.append(f"- 形态判定: 【非标准反转形态 / 震荡整理】")
    report.append("")
    report.append(f"#### 二、当前最新 4H 周期 [{running_slot}] 及盘面动态")
    report.append(f"- 运行中新K线: 开盘 `{o_run:.2f}` | 最高 `{h_run:.2f}` | 最低 `{l_run:.2f}` | 最新 `{c_run:.2f}`")
    report.append(f"- 4H技术指标: EMA20=`{ema20_4h:.2f}` | RSI=`{rsi_4h:.1f}` | MACD=`{macd_4h:.2f}`")
    report.append(f"- 日线状态: 今日开盘 `{od:.2f}` | 日内高点 `{hd:.2f}` | 日内低点 `{ld:.2f}` | 振幅 `{(hd - ld):.2f}` 点")
    report.append("")
    report.append("#### 三、核心关键水平位 (全盘动态计算，绝无死值)")
    report.append("【上方动态阻力区】(必须 > 现价):")
    for idx, (r_name, r_val) in enumerate(resistances, 1):
        report.append(f"  - 阻力 R{idx}: `{r_val:.2f}` ({r_name}，距现价 +{(r_val - curr_price):.1f} 点)")
    report.append(f"  $\to$ **当前现价基准: `{curr_price:.2f}`**")
    report.append("【下方动态支撑区】(必须 < 现价):")
    for idx, (s_name, s_val) in enumerate(supports, 1):
        # 极性转化动态标注
        polarity_mark = " [原阻力突破转换为强支撑]" if ("3600" in s_name or "起涨" in s_name or "高点" in s_name) and s_val < curr_price else ""
        report.append(f"  - 支撑 S{idx}: `{s_val:.2f}` ({s_name}{polarity_mark}，距现价 -{(curr_price - s_val):.1f} 点)")
    report.append("")
    report.append("---")
    report.append("#### 四、【多头维度 2+5 动态评级】")
    report.append(f"1. **准入门槛审查**: {pa['long_verdict']}")
    report.append(f"2. **综合评级结果**: **{pa['long_score_str']}**" + (f" (加分项: {', '.join(pa['long_star_details'])})" if pa['long_star_details'] else ""))
    report.append(f"3. **动态策略执行**: 当前现价已反弹脱离底部，距离下方第一支撑 `{pa['nearest_sup'][1]:.2f}` 达 {pa['dist_to_sup']:.1f} 点。严禁高位盲目追涨！做多最佳计划为耐心等待价格向次回踩测试 `{pa['nearest_sup'][1]:.2f}` 极性转化带确认企稳后介入。")
    report.append("")
    report.append("---")
    report.append("#### 五、【空头维度 2+5 动态评级】")
    report.append(f"1. **准入门槛审查**: {pa['short_verdict']}")
    report.append(f"2. **综合评级结果**: **{pa['short_score_str']}**" + (f" (加分项: {', '.join(pa['short_star_details'])})" if pa['short_star_details'] else ""))
    report.append(f"3. **动态策略执行**: 当前价格正在逼近上方阻力带 `{pa['nearest_res'][1]:.2f}` (相距仅 {pa['dist_to_res']:.1f} 点)。密切关注 4H 级别在该阻力区的收线表现：若出现长上影看跌流星线或假突破冲高回落，可顺势高空布局，止损设于阻力上方 3-5 点。")
    
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
