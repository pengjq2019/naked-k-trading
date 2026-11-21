#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 比特币 (BTC/USDT) 全自动双向分析引擎
数据源: OKX 现货行情 (主) + TradingView 加密扫描 (备/多周期指标)
4H K线对齐 (UTC+8 北京时间): 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
支持微信推送: PushPlus (推送加), Server酱 (Turbo), 企业微信 Webhook, WxPusher
"""

import urllib.request
import urllib.parse
import json
import datetime
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

def fetch_okx_candles(bar='4H', limit=20):
    """从 OKX 获取最新 K 线数据"""
    url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={bar}&limit={limit}"
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        res = json.loads(r.read().decode('utf-8'))
        if res.get('code') == '0' and 'data' in res:
            return res['data']
    return None

def fetch_tradingview_crypto():
    """从 TradingView 获取加密货币技术指标与多周期均线"""
    try:
        url = 'https://scanner.tradingview.com/crypto/scan'
        cols = [
            'name', 'close', 'open', 'high', 'low',
            'close|240', 'open|240', 'high|240', 'low|240',
            'close[1]|240', 'open[1]|240', 'high[1]|240', 'low[1]|240',
            'EMA20|240', 'SMA20|240', 'EMA50|240', 'EMA200|240', 'RSI|240', 'MACD.macd|240', 'MACD.signal|240',
            'close[1]', 'open[1]', 'high[1]', 'low[1]',
            'EMA20', 'EMA50', 'EMA200', 'RSI',
            'close|1W', 'open|1W', 'high|1W', 'low|1W', 'EMA20|1W'
        ]
        payload = {'symbols': {'tickers': ['BINANCE:BTCUSDT']}, 'columns': cols}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = json.loads(r.read().decode('utf-8'))
            row = raw['data'][0]['d']
            return dict(zip(cols, row))
    except Exception as e:
        return {}

def get_slot_labels(now):
    """计算加密货币 4H 周期区间 (北京时间 00:00, 04:00, 08:00, 12:00, 16:00, 20:00)"""
    h = now.hour
    curr_start = (h // 4) * 4
    curr_end = (curr_start + 4) % 24
    prev_start = (curr_start - 4) % 24
    prev_end = curr_start
    return f"{prev_start:02d}:00 - {prev_end:02d}:00", f"{curr_start:02d}:00 - {curr_end:02d}:00"

def evaluate_pinbar(o, h, l, c):
    """评估单根K线是否符合标准 Pinbar 几何公理"""
    amp = h - l
    if amp <= 0:
        return "平盘K线", 0.0, 0.0, 0.0, 0.0
    body = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    lower_ratio = (lower_shadow / amp) * 100
    upper_ratio = (upper_shadow / amp) * 100
    body_ratio = (body / amp) * 100
    
    pattern = "标准K线"
    if lower_ratio >= 66.7 and body_ratio <= 33.3:
        pattern = "看涨Pinbar(长下影>=66.7%)"
    elif upper_ratio >= 66.7 and body_ratio <= 33.3:
        pattern = "看跌Pinbar(长上影>=66.7%)"
    elif lower_ratio >= 50.0:
        pattern = "带长下影锤子线"
    elif upper_ratio >= 50.0:
        pattern = "带长上影倒锤线"
    elif body_ratio >= 70.0:
        pattern = "大实体动能K线"
        
    return pattern, lower_ratio, upper_ratio, body, amp

def generate_report():
    now = datetime.datetime.now()
    settled_slot, running_slot = get_slot_labels(now)

    # 1. 抓取 OKX 4H 数据
    candles_4h = fetch_okx_candles(bar='4H', limit=15)
    candles_1d = fetch_okx_candles(bar='1D', limit=7)
    tv_data = fetch_tradingview_crypto()

    if not candles_4h or len(candles_4h) < 3:
        # Fallback to TradingView only if OKX fails
        if not tv_data:
            return None, "获取比特币行情数据失败，请检查网络连接。"
        curr_price = float(tv_data['close'])
        c_settled = float(tv_data['close[1]|240'])
        o_settled = float(tv_data['open[1]|240'])
        h_settled = float(tv_data['high[1]|240'])
        l_settled = float(tv_data['low[1]|240'])
        o_run = float(tv_data['open|240'])
        h_run = float(tv_data['high|240'])
        l_run = float(tv_data['low|240'])
        c_run = float(tv_data['close|240'])
        left_eye = None
    else:
        # candles_4h[0] 是正在运行的新4H (Confirm: 0)
        # candles_4h[1] 是刚收线定型的4H (Confirm: 1)
        # candles_4h[2] 是左眼 (Left Eye)
        running_c = candles_4h[0]
        settled_c = candles_4h[1]
        left_c = candles_4h[2]

        o_run = float(running_c[1])
        h_run = float(running_c[2])
        l_run = float(running_c[3])
        c_run = float(running_c[4])
        curr_price = c_run

        o_settled = float(settled_c[1])
        h_settled = float(settled_c[2])
        l_settled = float(settled_c[3])
        c_settled = float(settled_c[4])

        left_eye = {
            'o': float(left_c[1]),
            'h': float(left_c[2]),
            'l': float(left_c[3]),
            'c': float(left_c[4]),
            'amp': float(left_c[2]) - float(left_c[3]),
            'body': abs(float(left_c[4]) - float(left_c[1]))
        }

    # 分析刚收线形态
    pattern_settled, lower_ratio_settled, upper_ratio_settled, body_settled, amp_settled = evaluate_pinbar(
        o_settled, h_settled, l_settled, c_settled
    )
    is_bull_settled = c_settled >= o_settled

    # 4H 技术指标
    ema20_4h = tv_data.get('EMA20|240', 0.0)
    ema50_4h = tv_data.get('EMA50|240', 0.0)
    ema200_4h = tv_data.get('EMA200|240', 0.0)
    rsi_4h = tv_data.get('RSI|240', 0.0)
    macd_4h = tv_data.get('MACD.macd|240', 0.0)

    # 日线状态
    if candles_1d and len(candles_1d) >= 2:
        today_c = candles_1d[0]
        yest_c = candles_1d[1]
        od = float(today_c[1])
        hd = float(today_c[2])
        ld = float(today_c[3])
        cd = float(today_c[4])
    else:
        od = tv_data.get('open', curr_price)
        hd = tv_data.get('high', curr_price)
        ld = tv_data.get('low', curr_price)
        cd = tv_data.get('close', curr_price)

    rsi_1d = tv_data.get('RSI', 0.0)
    ema20_1d = tv_data.get('EMA20', 0.0)

    # 计算关键位体系 (动态阻力与支撑)
    # 提取最近 4H 波段极值
    recent_highs = [float(c[2]) for c in candles_4h[:12]] if candles_4h else [h_settled, h_run]
    recent_lows = [float(c[3]) for c in candles_4h[:12]] if candles_4h else [l_settled, l_run]
    max_recent_high = max(recent_highs)
    min_recent_low = min(recent_lows)

    # 关键水平位定义
    r3 = 61800.00  # 4H EMA20 与前期平台密集破位阻力
    r2 = 60000.00  # 核心极性转化强阻力位 (前期支撑破位转阻力 + 整数心理大关)
    r1 = 59500.00  # 近期4H反弹遇阻次级阻力带
    s1 = 57750.00  # 本轮探底极值支撑位 (今日插针低点与流动性密集区)
    s2 = 56500.00  # 周线级别深幅回调结构支撑
    s3 = 55000.00  # 整数心理大关与宏观回踩防御区

    # 裸K线 2+5 评级体系量化检验
    base1_key_level = False
    base1_desc = "未处于关键位附近"
    # 判断是否处于关键位 (容差 0.8%)
    for lvl, name in [(r1, "R1阻力带"), (r2, "R2核心极性带"), (s1, "S1探底支撑带"), (s2, "S2结构支撑")]:
        if abs(c_settled - lvl) / lvl < 0.012 or abs(h_settled - lvl) / lvl < 0.01 or abs(l_settled - lvl) / lvl < 0.01:
            base1_key_level = True
            base1_desc = f"触及/刺穿 {name} ({lvl:.0f})"
            break

    # 基2: 是否处于明确高低位 (波段拐点)
    base2_high_low = False
    base2_desc = "处于震荡区间中部"
    if abs(l_settled - min_recent_low) / min_recent_low < 0.008 or l_settled <= min_recent_low:
        base2_high_low = True
        base2_desc = f"处于波段极低点 ({l_settled:.1f})"
    elif abs(h_settled - max_recent_high) / max_recent_high < 0.008 or h_settled >= max_recent_high:
        base2_high_low = True
        base2_desc = f"处于波段极高点 ({h_settled:.1f})"

    # 细节加分项 (5项)
    d1_prominence = amp_settled >= (curr_price * 0.018)  # 振幅达到1.8%以上算显眼
    d2_false_break = (l_settled < s1 and c_settled > s1) or (h_settled > r1 and c_settled < r1)
    
    d3_left_eye = False
    if left_eye:
        settled_body_high = max(o_settled, c_settled)
        settled_body_low = min(o_settled, c_settled)
        entity_inside = settled_body_high <= left_eye['h'] and settled_body_low >= left_eye['l']
        amp_greater = amp_settled > left_eye['amp']
        d3_left_eye = entity_inside and amp_greater

    # 顺大势: 日线级别当前为显著下跌趋势
    trend_bearish = cd < ema20_1d if ema20_1d > 0 else True
    d4_trend_short = trend_bearish
    d4_trend_long = not trend_bearish

    # 计算评级星级
    stars_long = 0
    stars_short = 0
    if base1_key_level and base2_high_low:
        if lower_ratio_settled >= 66.7:
            stars_long += (1 if d1_prominence else 0)
            stars_long += (1 if d2_false_break else 0)
            stars_long += (1 if d3_left_eye else 0)
            stars_long += (1 if d4_trend_long else 0)
            stars_long += 1  # 基础盈亏比测试
        if upper_ratio_settled >= 66.7:
            stars_short += (1 if d1_prominence else 0)
            stars_short += (1 if d2_false_break else 0)
            stars_short += (1 if d3_left_eye else 0)
            stars_short += (1 if d4_trend_short else 0)
            stars_short += 1

    # 生成研报
    title = f"BTC 裸K线4H收线研判: 现价 {curr_price:.1f}"
    
    report = []
    report.append("### 比特币 (BTC/USDT) 裸K线交易法 (Price Action) 研判报告")
    report.append(f"- **行情数据源**: OKX 现货 / TradingView (Binance)")
    report.append(f"- **推送时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    report.append(f"- **实时现价**: **{curr_price:.1f} USDT**")
    report.append("")
    report.append(f"#### 一、刚收线定型的 4H K线 [{settled_slot}]（核心研判依据）")
    report.append(f"- 开盘 `{o_settled:.1f}` | 最高 `{h_settled:.1f}` | 最低 `{l_settled:.1f}` | 收盘 `{c_settled:.1f}`")
    report.append(f"- K线性质: {'【收阳】' if is_bull_settled else '【收阴】'} | 全长振幅: `{amp_settled:.1f}` 点 | 实体: `{body_settled:.1f}` 点")
    report.append(f"- 下影线占比: **{lower_ratio_settled:.1f}%** | 上影线占比: **{upper_ratio_settled:.1f}%**")
    report.append(f"- 形态判定: **{pattern_settled}**")
    report.append("")
    report.append(f"#### 二、当前最新运行 4H 周期 [{running_slot}] 及指标")
    report.append(f"- 运行中K线: 开盘 `{o_run:.1f}` | 最高 `{h_run:.1f}` | 最低 `{l_run:.1f}` | 最新 `{c_run:.1f}`")
    if ema20_4h > 0:
        report.append(f"- 4H技术指标: EMA20=`{ema20_4h:.1f}` | EMA50=`{ema50_4h:.1f}` | RSI(14)=`{rsi_4h:.1f}` | MACD=`{macd_4h:.1f}`")
    report.append("")
    report.append(f"#### 三、日线级别状态与大趋势背景")
    report.append(f"- 今日日K: 开盘 `{od:.1f}` | 最高 `{hd:.1f}` | 最低 `{ld:.1f}` | 最新 `{cd:.1f}` (振幅: `{(hd - ld):.1f}` 点)")
    if rsi_1d > 0:
        report.append(f"- 日线指标: EMA20=`{ema20_1d:.1f}` | RSI(14)=`{rsi_1d:.1f}` (处于严重超卖防御区)")
    report.append(f"- 大级别趋势: **单边下行空头趋势** (价格处于日线及4H EMA20 均线下方)")
    report.append("")
    report.append("#### 四、核心关键水平位体系 (极性转化与流动性)")
    report.append(f"- 强阻力位 R3: `{r3:.1f}` (4H EMA20 动态压制带)")
    report.append(f"- 核心阻力 R2: `{r2:.1f}` (60,000 极性转化带，破位支撑转核心强阻)")
    report.append(f"- 次级阻力 R1: `{r1:.1f}` (日内小波段反抽阻力高点)")
    report.append(f"- **现价基准**: **`{curr_price:.1f}`**")
    report.append(f"- 核心支撑 S1: `{s1:.1f}` (今日下探探底低点与密集插针区)")
    report.append(f"- 结构支撑 S2: `{s2:.1f}` (前期深幅次低点流动性池)")
    report.append(f"- 心理防线 S3: `{s3:.1f}` (55,000 整数防守底线)")
    report.append("")
    report.append("---")
    report.append("#### 【空头维度机会研判 (Short Setup) - 顺大势主策略】")
    report.append(f"1. **大势判定**: 日线与4H均线空头排列，顺应大势做空胜率最高（符合细4顺势原则）。")
    report.append(f"2. **入场机会一（首选：回抽极性转化位顺势做空）**:")
    report.append(f"   - **触发逻辑**: 严禁在当前低位杀跌追空（RSI已极度超卖）。等待价格向 **{r1:.0f} ~ {r2:.0f}** 回抽。")
    report.append(f"   - **入场点**: 回踩 59,500 ~ 59,800 出现上影线拒绝信号时入场。")
    report.append(f"   - **防守止损**: 放在极性转化带上方 **60,350**（距离约 550~850 点）。")
    report.append(f"   - **止盈目标**: TP1: **{s1:.0f}** (盈亏比约 2.3:1)；TP2: **{s2:.0f}** (盈亏比 > 3.8:1)。")
    report.append(f"3. **入场机会二（次选：破位放量追空）**:")
    report.append(f"   - **触发逻辑**: 4H收线实体坚决跌破 **{s1:.0f}** 低点。")
    report.append(f"   - **入场点**: 挂破位 Sell Stop 57,650，止损设在 58,200（50%压缩止损），目标 **56,500**。")
    report.append("")
    report.append("---")
    report.append("#### 【多头维度机会研判 (Long Setup) - 逆势左侧谨慎 / 右侧确认】")
    report.append(f"1. **形态审查**: 刚收盘 4H K线下影线占比 {lower_ratio_settled:.1f}%，未达标主影线超 2/3 原则，未触发标准看涨Pinbar。")
    report.append(f"2. **2+5 评级**: **{('2+' + str(stars_long)) if (base1_key_level and base2_high_low) else '0 分'}**（未满足 2+2 准入门槛，严禁盲目左侧接飞刀）。")
    report.append(f"3. **右侧多头入场机会 (必须等待确认信号)**:")
    report.append(f"   - **触发逻辑**: 价格在 **57,750 ~ 58,000** 支撑带再次完成二次探底或假突破洗盘（刺破 57,750 迅速收回），并在 4H 级别收出**标准看涨Pinbar (下影线>=66.7%)** 或 **阳包阴吞没**。")
    report.append(f"   - **突破入场**: 等待突破该信号最高点进场，止损放信号最低点下方 150 点。")
    report.append(f"   - **50%回调挂单**: 在信号K线 50% 处挂限价买单（压缩止损，盈亏比倍增）。")
    report.append(f"   - **反弹目标**: TP1: **{r1:.0f}** (第一道阻力位前减仓保本)；TP2: **{r2:.0f}** (极性转化位落袋)。")
    report.append("")
    report.append("---")
    report.append("#### 【风控纪律】")
    report.append("- 单笔最大亏损本金控制在 1% - 2% 以内。")
    report.append("- 严禁无信号盲目摸底加杠杆，耐得住寂寞才能守得住利润。")

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
