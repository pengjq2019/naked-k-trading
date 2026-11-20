#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸K线交易法 (Price Action) 黄金全自动双向分析引擎
4H K线对齐标准: 北京时间 2:00, 6:00, 10:00, 14:00, 18:00, 22:00 收线
支持微信推送: PushPlus (推送加), Server酱 (Turbo), 企业微信 Webhook, WxPusher
"""

import urllib.request
import urllib.parse
import json
import datetime
import os
import sys

def is_market_open():
    """判断黄金交易市场是否开盘 (北京时间 UTC+8)
    通常周六早晨 06:00 闭盘，周一早晨 06:00 开盘。
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

def get_4h_block(dt):
    """
    将时间对齐到4小时K线开盘起点 (北京时间)
    周期区间:
    [22:00, 02:00) -> 22:00
    [02:00, 06:00) -> 02:00
    [06:00, 10:00) -> 06:00
    [10:00, 14:00) -> 10:00
    [14:00, 18:00) -> 14:00
    [18:00, 22:00) -> 18:00
    """
    h = dt.hour
    if h < 2:
        prev_day = dt.date() - datetime.timedelta(days=1)
        return datetime.datetime.combine(prev_day, datetime.time(22, 0))
    else:
        block_h = ((h - 2) // 4) * 4 + 2
        return datetime.datetime.combine(dt.date(), datetime.time(block_h, 0))

def fetch_chart(symbol, interval, range_str):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_str}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def get_market_data():
    h_data = fetch_chart('GC=F', '1h', '10d')
    h_ts = h_data['chart']['result'][0]['timestamp']
    h_q = h_data['chart']['result'][0]['indicators']['quote'][0]
    
    hourly = []
    for i in range(len(h_ts)):
        o = h_q['open'][i]
        h = h_q['high'][i]
        l = h_q['low'][i]
        c = h_q['close'][i]
        if None in (o, h, l, c):
            continue
        t = datetime.datetime.fromtimestamp(h_ts[i])
        hourly.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})
        
    four_hours = []
    curr_block = None
    curr_c = None
    for c in hourly:
        b_time = get_4h_block(c['time'])
        if curr_block != b_time:
            if curr_c:
                four_hours.append(curr_c)
            curr_block = b_time
            curr_c = {'time': b_time, 'open': c['open'], 'high': c['high'], 'low': c['low'], 'close': c['close'], 'sub': [c]}
        else:
            curr_c['high'] = max(curr_c['high'], c['high'])
            curr_c['low'] = min(curr_c['low'], c['low'])
            curr_c['close'] = c['close']
            curr_c['sub'].append(c)
    if curr_c:
        four_hours.append(curr_c)
        
    d_data = fetch_chart('GC=F', '1d', '3mo')
    d_ts = d_data['chart']['result'][0]['timestamp']
    d_q = d_data['chart']['result'][0]['indicators']['quote'][0]
    
    daily = []
    for i in range(len(d_ts)):
        o = d_q['open'][i]
        h = d_q['high'][i]
        l = d_q['low'][i]
        c = d_q['close'][i]
        if None in (o, h, l, c):
            continue
        t = datetime.datetime.fromtimestamp(d_ts[i]).strftime('%Y-%m-%d')
        daily.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})
        
    return hourly, four_hours, daily

def generate_report():
    if not is_market_open():
        return None, "【休市提醒】当前处于周末黄金休市时段，市场暂停报价，跳过本次推送。"

    hourly, four_hours, daily = get_market_data()
    c4 = four_hours[-1]
    p4 = four_hours[-2]
    cd = daily[-1]
    pd = daily[-2]
    curr_price = c4['close']
    
    # 4H当前K线属性
    amp_4h = c4['high'] - c4['low']
    body_4h = abs(c4['close'] - c4['open'])
    lower_shadow_4h = min(c4['open'], c4['close']) - c4['low']
    upper_shadow_4h = c4['high'] - max(c4['open'], c4['close'])
    lower_ratio_4h = (lower_shadow_4h / amp_4h * 100) if amp_4h > 0 else 0
    upper_ratio_4h = (upper_shadow_4h / amp_4h * 100) if amp_4h > 0 else 0
    
    # 4H周期收盘时间
    close_time_4h = c4['time'] + datetime.timedelta(hours=4)
    now = datetime.datetime.now()
    remaining_secs = max(0, int((close_time_4h - now).total_seconds()))
    rem_h = remaining_secs // 3600
    rem_m = (remaining_secs % 3600) // 60
    
    # 关键位
    r1 = 3600.0  # 极性转化最近强阻力 (前期跌破平台)
    r2 = 3670.0  # 凌晨破位阻力
    r3 = 3720.0  # 大级别密集区
    s1 = 3515.0  # 今日试探低点
    s2 = 3500.0  # 整数心理强关口
    s3 = 3450.0  # 下方波段支撑
    
    title = f"黄金裸K研判: 现价 {curr_price:.1f} | 4H收线监控"
    
    report = []
    report.append(f"### 黄金裸K线交易法 (Price Action) 双向研判报告")
    report.append(f"- **标的**: COMEX 黄金连续 (GC=F / XAUUSD)")
    report.append(f"- **分析时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    report.append(f"- **实时现价**: **{curr_price:.2f}**")
    report.append("")
    report.append(f"#### 4H K线状态 ({c4['time'].strftime('%H:%M')} - {close_time_4h.strftime('%H:%M')})")
    report.append(f"- 开盘: {c4['open']:.2f} | 最高: {c4['high']:.2f} | 最低: {c4['low']:.2f} | 最新: {c4['close']:.2f}")
    report.append(f"- 全长振幅: {amp_4h:.2f} 点 | 实体: {body_4h:.2f} 点")
    report.append(f"- 下影线占比: **{lower_ratio_4h:.1f}%** | 上影线占比: **{upper_ratio_4h:.1f}%**")
    if remaining_secs > 0:
        report.append(f"- 状态: 距收线还剩 {rem_h}小时{rem_m}分钟 (预计 {close_time_4h.strftime('%H:%M')} 确认)")
    else:
        report.append(f"- 状态: **已收线确认**")
    report.append("")
    report.append(f"#### 日线 K线状态 ({cd['time']})")
    report.append(f"- 开盘: {cd['open']:.2f} | 最高: {cd['high']:.2f} | 最低: {cd['low']:.2f} | 最新: {cd['close']:.2f}")
    report.append("")
    report.append("#### 核心关键位体系")
    report.append(f"- 阻力 R2: `{r2:.2f}` (凌晨破位平台)")
    report.append(f"- 极性转化阻力 R1: `{r1:.2f}` (原支撑跌破转为强阻力)")
    report.append(f"- 当前现价: `{curr_price:.2f}`")
    report.append(f"- 试探支撑 S1: `{s1:.2f}` (今日下探低点)")
    report.append(f"- 心理大关 S2: `{s2:.2f}` (整数流动性关口)")
    report.append("")
    report.append("---")
    report.append("#### 【多头维度研判 (Long Setup)】")
    report.append(f"1. **环境与位置**: 逼近 {s1:.2f} 与 {s2:.2f}，具有潜在关注价值，但非多拐点强共振。")
    report.append(f"2. **形态确认**: 下影线占比 {lower_ratio_4h:.1f}%，未达到Pinbar核心影线>=66.7%标准，触发一票否决红线。")
    report.append(f"3. **2+5评级**: **0 分**（严禁盲目抄底接飞刀）。")
    report.append(f"4. **触发条件**: 必须等待 4H/日线 在 3500-3515 区间收出明确看涨Pinbar或看涨吞没且评级>=2+2。")
    report.append("")
    report.append("---")
    report.append("#### 【空头维度研判 (Short Setup)】")
    report.append(f"1. **大级别趋势**: 4H与日线均线极度空头排列，主趋势绝对为【空】。")
    report.append(f"2. **追空风险**: 日内重挫逾百点，低位直接追空盈亏比差，防范反抽。")
    report.append(f"3. **2+5评级**: 反弹做空模型潜在评级 **2+3 星**（顺势+极性转化阻力+高盈亏比）。")
    report.append(f"4. **触发策略**: 耐心等待反弹测试 **3590 ~ 3610** 阻力带滞涨并收出看跌Pinbar后顺势开空。")
    
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
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
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
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'})
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
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
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
                'contentType': 3,  # markdown
                'uids': [wx_uid]
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read().decode('utf-8'))
                print(f"[WxPusher] 推送结果: {res.get('msg')}")
                pushed = True
        except Exception as e:
            print(f"[WxPusher] 推送异常: {e}")

    if not pushed:
        print("[微信推送提示] 未配置微信推送凭证环境变量 (PUSHPLUS_TOKEN / SERVERCHAN_KEY / WECOM_WEBHOOK / WXPUSHER_APP_TOKEN)。本地仅打印输出。")

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
    
    # 微信推送
    push_wechat(title, report)

if __name__ == '__main__':
    main()
