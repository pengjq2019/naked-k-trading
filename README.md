# 裸K线价格行为交易系统 (Price Action Trading System)

本系统基于许佳聪著《裸K线交易法：价格行为(Price Action)全面详解》构建，融合机构订单流痕迹、关键位极性转化体系与量化 **2+5 信号评级模型**，全自动监控高流动性标的（比特币 BTC/USDT 与 黄金 XAU/USD CFD），在每根 4 小时 K 线收盘后立即锁定形态、量化研判并推送微信。

---

## 核心架构与功能

1. **4小时级别价格行为自动化研判**:
   - **比特币 (BTC/USDT)**: 数据对齐标准加密周期（北京时间 00:00, 04:00, 08:00, 12:00, 16:00, 20:00），在收线后第 5 分钟全自动执行研判。
   - **现货黄金 (XAU/USD CFD)**: 嘉盛 (Forex.com) 现货标准数据源，周末自动过滤休市时段。
2. **裸K线几何公理严格量化**:
   - 区分刚收线定型的 4H K线（形态锁定，核心交易依据）与当前运行中K线（盘中动态）。
   - 量化实体占比、主影线占比（Pinbar 必须满足主影线 $\ge 66.7\%$）。
   - 左眼（Left Eye）包容性与振幅优劣对比。
3. **2+5 评级体系与双向机会推演**:
   - **两项基本门槛（一票否决）**: 是否触及大级别关键位、是否处于明显高低位波段拐点。
   - **五项细节加分**: 显眼度、假突破洗盘、左眼包容与幅度优于左眼、顺应大级别趋势、突破盈亏比 $\ge 1.5:1$。
   - 准入门槛：必须达到 $\ge 2+2$ 星级方可触发入场计划。
   - 明确输出：首选入场点（突破入场/50%回调挂单）、防守止损位、目标止盈位（TP1/TP2）与盈亏比。
4. **多通道微信实时推送**:
   - PushPlus (推送加)
   - Server酱 Turbo
   - 企业微信机器人 Webhook
   - WxPusher

---

## 项目目录结构

```text
├── .github/
│   └── workflows/
│       ├── btc_alert.yml       # 比特币 4H 收线自动推送工作流 (00:05, 04:05, 08:05, 12:05, 16:05, 20:05)
│       └── gold_alert.yml      # 黄金 4H 收线自动推送工作流
├── knowledge_base/             # 裸K线交易法系统性知识库
│   ├── 01_核心哲学与交易系统/
│   ├── 02_K线语言与形态学/
│   ├── 03_关键位体系/
│   ├── 04_裸K交易法则_Price_Action/
│   ├── 05_资金管理与加仓模型/
│   ├── 06_复盘与心理控制/
│   └── 07_实战速查手册/
├── scripts/
│   ├── analyze_btc.py          # 比特币 4H 裸K价格行为双向分析与推送引擎
│   └── analyze_gold.py         # 黄金 4H 裸K价格行为双向分析与推送引擎
├── .env.example                # 环境变量配置模板
└── README.md                   # 项目系统总览
```

---

## GitHub Actions 自动推送配置

进入 GitHub 仓库页面 -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**，添加以下密钥（至少配置其中一项）：

| Secret 名称 | 说明 | 对应平台 |
| :--- | :--- | :--- |
| `PUSHPLUS_TOKEN` | PushPlus 用户 Token | [pushplus.plus](https://www.pushplus.plus/) |
| `SERVERCHAN_KEY` | Server酱 SendKey | [sct.ftqq.com](https://sct.ftqq.com/) |
| `WECOM_WEBHOOK` | 企业微信群机器人 Webhook 地址 | 企业微信 |
| `WXPUSHER_APP_TOKEN` | WxPusher AppToken | [wxpusher.zjiecode.com](https://wxpusher.zjiecode.com/) |
| `WXPUSHER_UID` | WxPusher 用户 UID | WxPusher 关注二维码获取 |

---

## 本地运行

```bash
# 执行比特币 4H 裸K分析与推送
python scripts/analyze_btc.py

# 执行黄金 4H 裸K分析与推送
python scripts/analyze_gold.py
```
