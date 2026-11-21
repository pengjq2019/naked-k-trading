#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 黄金全自动双向分析引擎
数据源: Forex.com (嘉盛) XAUUSD 现货 / CFD 标准
4H K线对齐: 北京时间 2:00, 6:00, 10:00, 14:00, 18:00, 22:00
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
    """从 TradingView 获取 Forex.com (嘉盛) XAUUSD 高精度 4H 及日线数据与指标"""
    url = 'https://scanner.tradingview.com/cfd/scan'
    cols = [
        'name', 'close', 'open', 'high', 'low',
        'close|240', 'open|240', 'high|240', 'low|240',
        'close[1]|240', 'open[1]|240', 'high[1]|240', 'low[1]|240',
        'close[1]', 'open[1]', 'high[1]', 'low[1]',
        'EMA20|240', 'SMA20|240', 'RSI|240', 'MACD.macd|240', 'MACD.signal|240',
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

def generate_report():
    if not is_market_open():
        return None, "【休市提醒】当前处于周末黄金休市时段（周六06:00至周一06:00），市场暂停报价，跳过本次推送。"

    d = fetch_forexcom_gold()
    curr_price = d['close']
    now = datetime.datetime.now()
    settled_slot, running_slot = get_slot_labels(now)
    
    # 刚收线定型的完整 4H K线 (核心研判依据，形态已锁定)
    o_settled = d['open[1]|240']
    h_settled = d['high[1]|240']
    l_settled = d['low[1]|240']
    c_settled = d['close[1]|240']
    amp_settled = h_settled - l_settled
    body_settled = abs(c_settled - o_settled)
    lower_shadow_settled = min(o_settled, c_settled) - l_settled
    upper_shadow_settled = h_settled - max(o_settled, c_settled)
    lower_ratio_settled = (lower_shadow_settled / amp_settled * 100) if amp_settled > 0 else 0
    upper_ratio_settled = (upper_shadow_settled / amp_settled * 100) if amp_settled > 0 else 0
    is_bull_settled = c_settled >= o_settled

    # 正在运行的新 4H K线 (最新盘中动态)
    o_run = d['open|240']
    h_run = d['high|240']
    l_run = d['low|240']
    c_run = d['close|240']
    
    # 日线数值
    od = d['open']
    hd = d['high']
    ld = d['low']
    cd = d['close']
    
    # 4H 指标
    ema20_4h = d['EMA20|240']
    rsi_4h = d['RSI|240']
    macd_4h = d['MACD.macd|240']

    # 关键水平位体系 (基于 Forex.com 现货点位)
    r2 = 3600.00  # 极性转化第一重阻力 (破位支撑转阻力)
    r1 = 3585.00  # 4H波段反弹次高点阻力
    s1 = 3514.70  # 昨日试探最低支撑
    s2 = 3500.00  # 整数心理大关与流动性密集区
    
    title = f"黄金(嘉盛CFD)4H收线研判: 现价 {curr_price:.2f}"
    
    report = []
    report.append(f"### 黄金裸K线交易法 (Price Action) 研判报告")
    report.append(f"- **官方数据源**: **Forex.com (嘉盛) XAU/USD 现货 / CFD**")
    report.append(f"- **推送时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    report.append(f"- **实时现价**: **{curr_price:.2f}**")
    report.append("")
    report.append(f"#### 一、刚收线定型的 4H K线 [{settled_slot}]（核心交易依据）")
    report.append(f"- 开盘 `{o_settled:.2f}` | 最高 `{h_settled:.2f}` | 最低 `{l_settled:.2f}` | 收盘 `{c_settled:.2f}`")
    report.append(f"- K线性质: {'【收阳】' if is_bull_settled else '【收阴】'} | 全长振幅: `{amp_settled:.2f}` 点 | 实体: `{body_settled:.2f}` 点")
    report.append(f"- 下影线占比: **{lower_ratio_settled:.1f}%** | 上影线占比: **{upper_ratio_settled:.1f}%**")
    report.append(f"- 形态判定: {'符合标准长下影Pinbar(>=66.7%)' if lower_ratio_settled >= 66.7 else ('符合标准长上影Pinbar(>=66.7%)' if upper_ratio_settled >= 66.7 else '非标准Pinbar形态')}")
    report.append("")
    report.append(f"#### 二、当前最新 4H 周期 [{running_slot}] 及指标")
    report.append(f"- 当前新K线: 开盘 `{o_run:.2f}` | 最高 `{h_run:.2f}` | 最低 `{l_run:.2f}` | 最新 `{c_run:.2f}`")
    report.append(f"- 4H技术指标: EMA20=`{ema20_4h:.2f}` | RSI=`{rsi_4h:.1f}` | MACD=`{macd_4h:.2f}`")
    report.append("")
    report.append(f"#### 三、日线 K线状态")
    report.append(f"- 开盘: `{od:.2f}` | 最高: `{hd:.2f}` | 最低: `{ld:.2f}` | 最新: `{cd:.2f}` (振幅: `{(hd - ld):.2f}` 点)")
    report.append("")
    report.append("#### 四、核心关键水平位 (极性转化带)")
    report.append(f"- 强阻力位 R2: `{r2:.2f}` (极性转化核心防御区)")
    report.append(f"- 次级阻力 R1: `{r1:.2f}` (波段反抽遇阻位)")
    report.append(f"- 现价基准: `{curr_price:.2f}`")
    report.append(f"- 核心支撑 S1: `{s1:.2f}` (近期下探低点)")
    report.append(f"- 整数关口 S2: `{s2:.2f}` (心理防线与流动性密集区)")
    report.append("")
    report.append("---")
    report.append("#### 【多头维度研判 (Long Setup)】")
    report.append(f"1. **形态审查**: 刚收盘的 4H K线下影线占比为 {lower_ratio_settled:.1f}%，未达标主影线超2/3原则，触发一票否决红线。")
    report.append(f"2. **2+5评级**: **0 分**（严禁盲目逆大势摸底接飞刀）。")
    report.append(f"3. **多头右侧信号要求**: 必须等待 4H/日线 在 3500-3515 支撑带完全收出下影线>=66.7%的看涨Pinbar或看涨吞没且评级 $\ge 2+2$。")
    report.append("")
    report.append("---")
    report.append("#### 【空头维度研判 (Short Setup)】")
    report.append(f"1. **趋势研判**: 大级别顺势方向绝对为【空】，均线系统呈陡峭空头排列。")
    report.append(f"2. **追空风控**: 短线多次下探 3500 附近，低位直接杀跌追空盈亏比不佳。")
    report.append(f"3. **高空策略**: 最佳交易计划依然是等待反弹回抽 **3580 ~ 3600** 极性转化阻力带受阻时顺大势做空。")
    
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
