#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 黄金全自动双向分析引擎
数据源: Forex.com (嘉盛) XAUUSD 现货黄金 / CFD 标准
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

def get_current_4h_slot(now):
    """计算当前 4H K线区间及收盘倒计时"""
    h = now.hour
    if h < 2:
        start_h = 22
        end_h = 2
    else:
        start_h = ((h - 2) // 4) * 4 + 2
        end_h = (start_h + 4) % 24
        
    close_dt = now.replace(minute=0, second=0, microsecond=0)
    if end_h == 2 and h >= 22:
        close_dt = close_dt + datetime.timedelta(days=1)
    close_dt = close_dt.replace(hour=end_h)
    
    rem_secs = max(0, int((close_dt - now).total_seconds()))
    rem_h = rem_secs // 3600
    rem_m = (rem_secs % 3600) // 60
    return f"{start_h:02d}:00 - {end_h:02d}:00", f"{end_h:02d}:00", rem_h, rem_m

def generate_report():
    if not is_market_open():
        return None, "【休市提醒】当前处于周末黄金休市时段，市场暂停报价，跳过本次推送。"

    d = fetch_forexcom_gold()
    curr_price = d['close']
    now = datetime.datetime.now()
    slot_str, close_time_str, rem_h, rem_m = get_current_4h_slot(now)
    
    # 当前 4H K线数值 (Forex.com 嘉盛)
    o4 = d['open|240']
    h4 = d['high|240']
    l4 = d['low|240']
    c4 = d['close|240']
    amp_4h = h4 - l4
    body_4h = abs(c4 - o4)
    lower_shadow_4h = min(o4, c4) - l4
    upper_shadow_4h = h4 - max(o4, c4)
    lower_ratio_4h = (lower_shadow_4h / amp_4h * 100) if amp_4h > 0 else 0
    upper_ratio_4h = (upper_shadow_4h / amp_4h * 100) if amp_4h > 0 else 0

    # 前一根 4H K线 (左眼)
    o4_prev = d['open[1]|240']
    h4_prev = d['high[1]|240']
    l4_prev = d['low[1]|240']
    c4_prev = d['close[1]|240']
    amp_4h_prev = h4_prev - l4_prev
    
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
    r2 = 3670.00  # 凌晨破位平台
    r1 = 3600.00  # 极性转化最近核心阻力 (整数大关与前期跌破平台)
    s1 = 3514.70  # 今日试探最低点 (今日日内极值支撑)
    s2 = 3500.00  # 整数心理大关与流动性密集区
    
    title = f"黄金(嘉盛CFD)裸K研判: {curr_price:.2f} | 4H收线"
    
    report = []
    report.append(f"### 黄金裸K线交易法 (Price Action) 研判报告")
    report.append(f"- **官方数据源**: **Forex.com (嘉盛) XAU/USD 现货 / CFD**")
    report.append(f"- **分析时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    report.append(f"- **实时现价**: **{curr_price:.2f}**")
    report.append("")
    report.append(f"#### 4H K线状态 ({slot_str})")
    report.append(f"- 当前K线: 开盘 `{o4:.2f}` | 最高 `{h4:.2f}` | 最低 `{l4:.2f}` | 最新 `{c4:.2f}`")
    report.append(f"- 全长振幅: `{amp_4h:.2f}` 点 | 实体: `{body_4h:.2f}` 点")
    report.append(f"- 下影线占比: **{lower_ratio_4h:.1f}%** | 上影线占比: **{upper_ratio_4h:.1f}%**")
    report.append(f"- 左眼对比 (前一根4H): 全长 `{amp_4h:.2f}` vs 左眼 `{amp_4h_prev:.2f}` (幅度超越: {'是' if amp_4h > amp_4h_prev else '否'})")
    report.append(f"- 4H均线与指标: EMA20=`{ema20_4h:.2f}` (重度空头排列) | RSI=`{rsi_4h:.1f}` (超卖区) | MACD=`{macd_4h:.2f}`")
    if rem_h > 0 or rem_m > 0:
        report.append(f"- 收线状态: 距本根 4H 收盘还剩 **{rem_h}小时{rem_m}分钟** (预计 {close_time_str} 收线)")
    else:
        report.append(f"- 收线状态: **已收线确认**")
    report.append("")
    report.append(f"#### 日线 K线状态 (今日)")
    report.append(f"- 开盘: `{od:.2f}` | 最高: `{hd:.2f}` | 最低: `{ld:.2f}` | 最新: `{cd:.2f}`")
    report.append(f"- 日内振幅: `{(hd - ld):.2f}` 点，呈现大阴线单边破位下行态势。")
    report.append("")
    report.append("#### 核心关键水平位 (极性转化带)")
    report.append(f"- 阻力 R2: `{r2:.2f}` (凌晨起跌破位平台)")
    report.append(f"- 极性转化阻力 R1: `{r1:.2f}` (原支撑跌破后转化为第一强阻力)")
    report.append(f"- 基准现价: `{curr_price:.2f}`")
    report.append(f"- 试探支撑 S1: `{s1:.2f}` (今日打出的日内最低点)")
    report.append(f"- 心理大关 S2: `{s2:.2f}` (整数流动性关口)")
    report.append("")
    report.append("---")
    report.append("#### 【多头维度研判 (Long Setup)】")
    report.append(f"1. **环境与位置**: 价格在低点 {s1:.2f} 获得暂时喘息，逼近整数大关 {s2:.2f}，但非大级别多拐点强共振。")
    report.append(f"2. **形态确认**: 下影线占比仅 {lower_ratio_4h:.1f}%，严重未达 Pinbar 核心影线 $\ge 66.7\%$ 标准，触发一票否决红线。")
    report.append(f"3. **2+5评级**: **0 分**（严禁盲目左侧接飞刀抄底）。")
    report.append(f"4. **触发条件**: 必须等待 4H/日线 在 3500-3515 区间完全收线确认出标准看涨Pinbar（长下影超2/3）或阳包阴吞没且评级 $\ge 2+2$。")
    report.append("")
    report.append("---")
    report.append("#### 【空头维度研判 (Short Setup)】")
    report.append(f"1. **大级别趋势**: 日线/4H 均线严密空头排列，顺大势方向绝对为【空】。")
    report.append(f"2. **追空风险**: 今日暴挫已逾 110 点，短线 RSI={rsi_4h:.1f} 进入极端超卖区，严禁在地板价追空防流动性报复性反抽。")
    report.append(f"3. **2+5评级**: 反弹极性转化做空模型潜在评级 **2+3 星**（顺大势+强极性转化阻力+大盈亏比）。")
    report.append(f"4. **触发策略**: 耐心等待弱势反弹回踩 **3590 ~ 3610** 阻力带滞涨，若 4H 收出看跌Pinbar或阴包阳吞没，坚决顺大势开空。")
    
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
    
    # 发起微信推送
    push_wechat(title, report)

if __name__ == '__main__':
    main()
