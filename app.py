# -*- coding: utf-8 -*-
"""
AI选股系统 - Streamlit Web界面
基于实时API数据，无本地数据库
"""
import io
import os
import re
import json
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime

# ========== Kimi API 配置 ==========
MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "sk-glzfuPUZClcjyMUebYUjgDcF26FyrONckkPX4taMY8dp3hW9")
KIMI_MODEL = "moonshot-v1-8k"

from core import (
    get_stock_list, get_realtime_quotes, get_kline,
    batch_get_klines, compute_indicators,
    is_risk_stock, is_hs_stock, get_intraday, get_financial_report,
)
from strategies import STRATEGIES, STRATEGY_NAMES, ADVANCED_CONDITIONS

# ========== 策略详情数据 ==========
STRATEGY_DETAIL_DATA = {
    "ma_bull": {
        "desc": "短期均线依次排列在长期均线上方，代表股价处于上升趋势",
        "strategy_conditions": [
            ("MA5 > MA10 > MA20 > MA60", "短期到长期均线依次向上排列",
             "MA（移动平均线）是N日收盘价的平均值。MA5是5日均线，MA10是10日均线。当短期均线在长期均线上方时，说明股价处于上升趋势"),
            ("股价 > MA5", "当前价格站在5日均线上方",
             "股价站在5日均线上方说明最近几天买盘强劲，短期趋势向上，买入意愿较强"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("市盈率范围", "最小PE ~ 最大PE", "根据市盈率估值筛选"),
            ("市净率范围", "最小PB ~ 最大PB", "根据市净率估值筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，存在财务风险或经营异常"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
    "macd_golden": {
        "desc": "MACD指标的DIF线从下向上穿越DEA线，代表上涨动能增强",
        "strategy_conditions": [
            ("昨日DIF ≤ DEA，今日DIF > DEA", "DIF线向上穿越DEA线形成金叉",
             "DIF是快线（12日EMA - 26日EMA），DEA是DIF的9日平滑线。金叉意味着短期上涨动能超过长期动能，买入信号"),
            ("MACD柱 > 0", "红色柱状体，多头力量占优",
             "MACD柱 = DIF - DEA。红柱表示DIF在DEA上方，多头力量强于空头；绿柱则相反"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("市盈率范围", "最小PE ~ 最大PE", "根据市盈率估值筛选"),
            ("市净率范围", "最小PB ~ 最大PB", "根据市净率估值筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，存在财务风险或经营异常"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
    "rsi_oversold": {
        "desc": "RSI指标进入超卖区域后回升，代表市场可能过度悲观后反弹",
        "strategy_conditions": [
            ("昨日RSI < 超卖线（默认30）", "RSI进入超卖区，市场情绪过度悲观",
             "RSI（相对强弱指标）衡量买卖力量对比，范围0-100。RSI<30表示超卖，意味着卖方力量过度释放"),
            ("今日RSI 回升至 超卖线~反弹上限", "RSI开始回升，买方力量回归",
             "RSI从超卖区回升，意味着卖压减弱，买方开始进场，股价有望从低位反弹"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("市盈率范围", "最小PE ~ 最大PE", "根据市盈率估值筛选"),
            ("市净率范围", "最小PB ~ 最大PB", "根据市净率估值筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，存在财务风险或经营异常"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
    "volume_price": {
        "desc": "股价明显上涨且成交量大幅放大，代表资金积极进场",
        "strategy_conditions": [
            ("当日涨幅 > 3%", "股价明显上涨，有资金推动",
             "涨幅超过3%说明当日有较强的买盘推动，不是无量空涨，上涨有成交量支撑"),
            ("成交量 > 昨日2倍", "成交量大幅放大，关注度骤增",
             "成交量是买卖双方成交的股票数量。比昨日放大2倍说明有大量资金入场，市场关注度骤增"),
            ("成交量 > 20日均量1.5倍", "成交量突破近期平均水平",
             "20日均量是过去20天平均成交量。突破均值说明当前交易活跃度远超近期常态，趋势可能发生变化"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("市盈率范围", "最小PE ~ 最大PE", "根据市盈率估值筛选"),
            ("市净率范围", "最小PB ~ 最大PB", "根据市净率估值筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，存在财务风险或经营异常"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
    "breakout": {
        "desc": "股价突破近期震荡区间上沿，上方套牢盘减少，上涨空间打开",
        "strategy_conditions": [
            ("今日收盘价创N日新高", "股价突破近期震荡区间上沿",
             "突破新高意味着股价脱离了之前的震荡区间，上方套牢筹码较少，继续上涨的压力减轻"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("市盈率范围", "最小PE ~ 最大PE", "根据市盈率估值筛选"),
            ("市净率范围", "最小PB ~ 最大PB", "根据市净率估值筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，存在财务风险或经营异常"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
    "kdj_golden": {
        "desc": "KDJ随机指标在低位区域形成金叉，上涨信号较强且空间较大",
        "strategy_conditions": [
            ("昨日K ≤ D，今日K > D", "K线向上穿越D线形成金叉",
             "KDJ是随机指标，K是快线，D是慢线。K上穿D为金叉，代表短期上涨动能增强"),
            ("K值 < 50", "KDJ处于低位区域，上涨空间较大",
             "KDJ在50以下为低位区域，说明股价尚未超买，仍有上涨空间。80以上为超买区，风险较大"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("市盈率范围", "最小PE ~ 最大PE", "根据市盈率估值筛选"),
            ("市净率范围", "最小PB ~ 最大PB", "根据市净率估值筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，存在财务风险或经营异常"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
    "fundamental": {
        "desc": "筛选低估值股票，市盈率、市净率均处于较低水平",
        "strategy_conditions": [
            ("市盈率 < 设定值", "估值较低，价格相对合理",
             "市盈率PE = 股价 / 每股收益。PE越低说明投资者为每元盈利支付的价格越少，估值越便宜"),
            ("市净率 < 设定值", "股价接近净资产，安全边际高",
             "市净率PB = 股价 / 每股净资产。PB<1表示股价低于公司账面价值，即使公司清算也有一定保障"),
            ("PE/PB 均为正数", "公司处于盈利状态",
             "负的PE表示公司亏损，负的PB表示资不抵债，都不是健康的基本面信号"),
        ],
        "global_filters": [
            ("价格区间", "¥最低 ~ ¥最高", "根据您设定的最低~最高价格范围筛选股票"),
            ("涨跌幅范围", "最小% ~ 最大%", "根据当日涨跌幅百分比筛选"),
            ("成交量范围", "最小 ~ 最大万手", "根据当日成交量筛选"),
            ("排除ST/退市", "自动过滤高风险股票", "ST股票是被特别处理的股票，通常存在财务问题"),
            ("仅沪深A股", "仅保留主板股票", "沪市600/601/603/688 + 深市000/002/300等主板代码"),
        ]
    },
}

# ========== 卡片辅助函数 ==========

def calc_match_score(strategy: str, row: pd.Series) -> int:
    """计算策略匹配度 (60-100)"""
    try:
        if strategy == "ma_bull":
            price = float(row.get("最新价", 0))
            ma5 = float(row.get("MA5", price))
            ma10 = float(row.get("MA10", ma5))
            ma20 = float(row.get("MA20", ma10))
            ma60 = float(row.get("MA60", ma20))
            if ma5 > ma10 > ma20 > ma60 and price > ma5 > 0:
                spread = (ma5 - ma60) / ma60 * 100
                return min(100, max(70, int(80 + spread * 0.5)))
            return 70
        elif strategy == "macd_golden":
            macd = float(row.get("MACD", 0))
            return min(100, max(70, int(85 + abs(macd) * 5)))
        elif strategy == "rsi_oversold":
            rsi = float(row.get("RSI今日", row.get("RSI", 50)))
            return min(100, max(70, int(95 - abs(rsi - 32))))
        elif strategy == "volume_price":
            chg = float(row.get("涨幅%", row.get("涨跌幅", 0)))
            return min(100, max(70, int(85 + chg * 1.5)))
        elif strategy == "breakout":
            pct = float(row.get("突破幅度%", 0))
            return min(100, max(70, int(85 + pct * 2)))
        elif strategy == "kdj_golden":
            k = float(row.get("K", 50))
            return min(100, max(70, int(95 - k * 0.4)))
        elif strategy == "fundamental":
            pe = float(row.get("市盈率", 30))
            pb = float(row.get("市净率", 3))
            score = 100 - pe * 0.3 - pb * 2
            return min(100, max(70, int(score)))
        elif strategy == "advanced":
            # 基于满足的条件数量计算匹配度（高级策略结果已满足所有选中条件）
            cond_count = 0
            for key in ["MA5", "MACD", "MACD_Q", "MACD_Y", "RSI今日", "涨幅%", "突破幅度%", "K", "市盈率",
                        "营业总收入(亿)", "归母净利润(亿)", "扣非净利润(亿)", "净资产收益率", "销售毛利率"]:
                if key in row.index and pd.notna(row.get(key)):
                    cond_count += 1
            return min(100, max(75, 75 + cond_count * 3))
        return 85
    except Exception:
        return 85


def get_card_conditions(strategy: str, row: pd.Series) -> list:
    """生成卡片显示的条件列表，每个条件包含 name, met, detail"""
    conditions = []
    price = float(row.get("最新价", 0))

    if strategy == "ma_bull":
        ma5 = float(row.get("MA5", 0))
        ma10 = float(row.get("MA10", 0))
        ma20 = float(row.get("MA20", 0))
        ma60 = float(row.get("MA60", 0))
        conditions.append({
            "name": "均线多头排列",
            "met": ma5 > ma10 > ma20 > ma60,
            "detail": f"MA5>MA10>MA20>MA60：{ma5:.0f}>{ma10:.0f}>{ma20:.0f}>{ma60:.0f}"
        })
        conditions.append({
            "name": "股价站上MA5",
            "met": price > ma5,
            "detail": f"当前价 ¥{price:.2f} > MA5 ¥{ma5:.2f}"
        })
    elif strategy == "macd_golden":
        macd = float(row.get("MACD", 0))
        sig = float(row.get("MACD_signal", 0))
        hist = float(row.get("MACD_hist", macd - sig))
        conditions.append({
            "name": "MACD金叉",
            "met": macd > sig,
            "detail": f"DIF({macd:.3f}) > DEA({sig:.3f})"
        })
        conditions.append({
            "name": "MACD柱 > 0",
            "met": hist > 0,
            "detail": f"柱状体 = {hist:.3f}"
        })
    elif strategy == "rsi_oversold":
        rsi_yest = float(row.get("RSI昨日", 0))
        rsi_today = float(row.get("RSI今日", 0))
        conditions.append({
            "name": "RSI超卖回升",
            "met": 20 <= rsi_today <= 60,
            "detail": f"昨日RSI={rsi_yest:.1f} → 今日RSI={rsi_today:.1f}"
        })
    elif strategy == "volume_price":
        chg = float(row.get("涨跌幅", row.get("涨幅%", 0)))
        vol_ratio = float(row.get("量比", 0))
        conditions.append({
            "name": f"涨幅>{chg:.1f}%",
            "met": chg > 3,
            "detail": f"当日涨幅 {chg:.2f}%（策略要求>3%）"
        })
        conditions.append({
            "name": f"量比{vol_ratio:.1f}",
            "met": vol_ratio > 1,
            "detail": f"量比 {vol_ratio:.2f}（>1表示放量）"
        })
    elif strategy == "breakout":
        breakout_pct = float(row.get("突破幅度%", 0))
        conditions.append({
            "name": "突破近期新高",
            "met": breakout_pct > 0,
            "detail": f"突破幅度 {breakout_pct:.2f}%"
        })
    elif strategy == "kdj_golden":
        k = float(row.get("K", 50))
        d = float(row.get("D", 50))
        conditions.append({
            "name": "KDJ低位金叉",
            "met": k > d and k < 50,
            "detail": f"K({k:.1f}) > D({d:.1f})，K值<50"
        })
    elif strategy == "fundamental":
        pe = float(row.get("市盈率", 0))
        pb = float(row.get("市净率", 0))
        conditions.append({
            "name": "低市盈率",
            "met": pe > 0,
            "detail": f"PE = {pe:.2f}"
        })
        conditions.append({
            "name": "低市净率",
            "met": pb > 0,
            "detail": f"PB = {pb:.2f}"
        })
    elif strategy == "advanced":
        # 根据结果中存在的列，动态显示已满足的条件
        if pd.notna(row.get("MA5")):
            met = (row.get("MA5", 0) > row.get("MA10", 0) > row.get("MA20", 0) > row.get("MA60", 0) and
                   price > row.get("MA5", 0))
            conditions.append({
                "name": "均线多头排列",
                "met": met,
                "detail": f"MA5={row.get('MA5', 0):.2f} > MA10={row.get('MA10', 0):.2f} > MA20={row.get('MA20', 0):.2f} > MA60={row.get('MA60', 0):.2f}"
            })
        if pd.notna(row.get("MA60")):
            conditions.append({
                "name": "股价站上MA60",
                "met": price > row.get("MA60", 0),
                "detail": f"当前价 ¥{price:.2f} > MA60 ¥{row.get('MA60', 0):.2f}"
            })
        if pd.notna(row.get("MACD")):
            conditions.append({
                "name": "日线MACD>0",
                "met": row.get("MACD", 0) > row.get("MACD_signal", 0),
                "detail": f"DIF={row.get('MACD', 0):.3f} > DEA={row.get('MACD_signal', 0):.3f}"
            })
        if pd.notna(row.get("MACD_Q")):
            conditions.append({
                "name": "季线MACD>0",
                "met": row.get("MACD_Q", 0) > row.get("MACD_Q_signal", 0),
                "detail": f"MACD_Q={row.get('MACD_Q', 0):.3f} > Signal={row.get('MACD_Q_signal', 0):.3f}"
            })
        if pd.notna(row.get("MACD_Y")):
            conditions.append({
                "name": "年线MACD>0",
                "met": row.get("MACD_Y", 0) > row.get("MACD_Y_signal", 0),
                "detail": f"MACD_Y={row.get('MACD_Y', 0):.3f} > Signal={row.get('MACD_Y_signal', 0):.3f}"
            })
        if pd.notna(row.get("RSI今日")):
            conditions.append({
                "name": "RSI超卖反弹",
                "met": 20 <= row.get("RSI今日", 0) <= 60,
                "detail": f"RSI={row.get('RSI今日', 0):.1f}"
            })
        if pd.notna(row.get("涨幅%")):
            conditions.append({
                "name": "量价齐升",
                "met": row.get("涨幅%", 0) > 3,
                "detail": f"涨幅 {row.get('涨幅%', 0):.2f}%，量比 {row.get('量比', 0):.2f}"
            })
        if pd.notna(row.get("突破幅度%")):
            conditions.append({
                "name": "突破近期新高",
                "met": row.get("突破幅度%", 0) > 0,
                "detail": f"突破幅度 {row.get('突破幅度%', 0):.2f}%"
            })
        if pd.notna(row.get("K")):
            conditions.append({
                "name": "KDJ低位金叉",
                "met": row.get("K", 0) > row.get("D", 0) and row.get("K", 0) < 50,
                "detail": f"K={row.get('K', 0):.1f} > D={row.get('D', 0):.1f}"
            })
        if pd.notna(row.get("市盈率")):
            conditions.append({
                "name": "基本面低估值",
                "met": row.get("市盈率", 0) > 0 and row.get("市净率", 0) > 0,
                "detail": f"PE={row.get('市盈率', 0):.2f} PB={row.get('市净率', 0):.2f}"
            })
        if pd.notna(row.get("营业总收入(亿)")):
            conditions.append({
                "name": "营业总收入",
                "met": True,
                "detail": f"营收 {row.get('营业总收入(亿)', 0):.2f} 亿元"
            })
        if pd.notna(row.get("归母净利润(亿)")):
            conditions.append({
                "name": "归母净利润",
                "met": True,
                "detail": f"归母净利润 {row.get('归母净利润(亿)', 0):.4f} 亿元"
            })
        if pd.notna(row.get("扣非净利润(亿)")):
            conditions.append({
                "name": "扣非净利润",
                "met": True,
                "detail": f"扣非净利润 {row.get('扣非净利润(亿)', 0):.4f} 亿元"
            })
        if pd.notna(row.get("净资产收益率")):
            conditions.append({
                "name": "净资产收益率",
                "met": True,
                "detail": f"ROE {row.get('净资产收益率', 0):.2f}%"
            })
        if pd.notna(row.get("销售毛利率")):
            conditions.append({
                "name": "销售毛利率",
                "met": True,
                "detail": f"毛利率 {row.get('销售毛利率', 0):.2f}%"
            })

    # 全局过滤条件（所有策略通用）
    conditions.append({
        "name": "非ST/退市",
        "met": True,
        "detail": "风险等级：低"
    })
    return conditions


# ========== 页面配置 ==========
st.set_page_config(
    page_title="AI选股系统",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== CSS样式 ==========
st.markdown("""
<style>
    div[data-testid="stToolbar"] { display: none !important; }
    header[data-testid="stHeader"] { display: none !important; }
    button[kind="header"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    .stDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }

    .topbar {
        position: fixed; top: 0; left: 0; right: 0; height: 52px;
        background: linear-gradient(90deg, #0d47a1, #1565c0, #1976d2);
        color: white; display: flex; align-items: center; justify-content: space-between;
        padding: 0 28px; z-index: 999999; box-shadow: 0 2px 10px rgba(0,0,0,0.25);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .topbar-left { display: flex; align-items: center; gap: 14px; font-size: 17px; font-weight: 700; }
    .topbar-right { display: flex; align-items: center; gap: 16px; font-size: 13px; color: rgba(255,255,255,0.9); }
    .topbar-tag { background: rgba(255,255,255,0.18); padding: 3px 10px; border-radius: 10px; font-size: 11px; }
    .live-tag { background: #4caf50; color: #fff; padding: 2px 8px; border-radius: 8px; font-size: 10px; font-weight: 700; }

    .block-container { padding-top: 64px !important; }

    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(90deg, #1565c0, #42a5f5) !important;
        border: none !important; font-weight: 600 !important;
    }

    /* Tooltip */
    .tooltip-icon {
        position: relative;
        display: inline-block;
        cursor: help;
        color: #1976d2;
        font-size: 13px;
        font-weight: bold;
        margin-left: 3px;
    }
    .tooltip-icon .tooltiptext {
        visibility: hidden;
        width: 260px;
        background-color: #263238;
        color: #fff;
        text-align: left;
        border-radius: 8px;
        padding: 10px 12px;
        position: absolute;
        z-index: 9999999;
        bottom: 125%;
        left: 50%;
        margin-left: -130px;
        opacity: 0;
        transition: opacity 0.25s;
        font-size: 12px;
        line-height: 1.6;
        font-weight: normal;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .tooltip-icon .tooltiptext::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -5px;
        border-width: 5px;
        border-style: solid;
        border-color: #263238 transparent transparent transparent;
    }
    .tooltip-icon:hover .tooltiptext {
        visibility: visible;
        opacity: 1;
    }

    /* 策略详情 */
    .detail-section-title {
        font-weight: 600;
        margin: 8px 0 4px 0;
        font-size: 12px;
    }
    .detail-section-strategy { color: #1565c0; }
    .detail-section-global { color: #666; }
    .detail-cond-line {
        display: flex;
        align-items: flex-start;
        gap: 5px;
        margin: 4px 0;
        font-size: 12px;
        line-height: 1.6;
    }
    .detail-cond-check { color: #4caf50; font-weight: bold; flex-shrink: 0; }
    .detail-cond-text { flex: 1; }
    .detail-cond-sub { color: #888; font-size: 11px; }
    .detail-footer {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px dashed #ddd;
        color: #888;
        font-size: 11px;
        text-align: center;
    }

    /* 过滤条件区域 */
    .filter-section {
        background: #f8f9fa;
        border: 1px solid #e1e4e8;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 14px;
    }
    .filter-section h4 {
        margin: 0 0 10px 0;
        color: #333;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# ========== 顶部导航栏 ==========
st.markdown(f"""
<div class="topbar">
    <div class="topbar-left"><span>🤖</span><span>AI选股系统</span><span class="live-tag">实时数据</span></div>
    <div class="topbar-right">
        <span class="topbar-tag">📊 {len(STRATEGIES)}种策略</span>
        <span>🕐 {datetime.now().strftime('%m-%d %H:%M')}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ========== 加载股票列表 ==========
@st.cache_data(ttl=3600)
def _load_stocks_v3(_cache_bust="v3"):
    """加载股票列表 - v3 缓存版本"""
    df = get_stock_list()
    if df.empty or "名称" not in df.columns:
        raise RuntimeError("获取股票列表失败，请检查网络或数据源")
    return df

try:
    stock_list = _load_stocks_v3()
except Exception as e:
    st.error(f"⚠️ 加载股票列表时出错：{str(e)}")
    st.stop()

# ========== session_state 初始化 ==========
if "max_candidates" not in st.session_state:
    st.session_state.max_candidates = 800
if "show_inline_max_slider" not in st.session_state:
    st.session_state.show_inline_max_slider = False
if "show_kline_view" not in st.session_state:
    st.session_state.show_kline_view = False
# Agent / 多页面相关
if "current_page" not in st.session_state:
    st.session_state.current_page = "🏠 首页"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "user_pref" not in st.session_state:
    st.session_state.user_pref = {"strategy": "ma_bull", "filters": {}}

# ========== Agent 工具函数（ReAct：Thought -> Action -> Observation -> Answer）==========

# ========== 策略别名与上下文工具 ==========

# 【新增】自然语言条件映射表：支持用户用日常语言描述筛选条件
NL_CONDITION_MAP = {
    # 市值
    "市值": ["市值", "盘子", "盘子大小", "流通市值", "总市值"],
    "market_cap": ["market cap", "capitalization"],
    # 涨幅
    "涨幅": ["涨幅", "涨跌", "涨了多少", "今天涨", "最近涨", "涨得好的", "强势股"],
    "change_pct": ["涨跌幅", "涨跌幅度"],
    # MACD
    "MACD": ["macd", "MACD", "macd指标", "MACD指标"],
    "macd_golden": ["macd金叉", "MACD金叉", "macd 金叉", "金叉"],
    # 均线
    "均线": ["均线", "MA", "ma", "移动平均线", "均线多头", "多头排列"],
    "ma_bull": ["均线多头排列", "多头排列", "均线排列", "均线向上"],
    # 换手率
    "换手率": ["换手", "换手率", "成交活跃", "量能"],
    # 股价
    "股价": ["股价", "价格", "当前价", "多少钱"],
    # 成交量
    "成交量": ["成交量", "量能", "放量", "成交量放大", "量升"],
    "volume_price": ["量价齐升", "量价", "放量上涨", "量升价涨"],
    # 净利润/基本面
    "净利润": ["净利润", "盈利", " earnings", "扣非净利润", "归母净利润"],
    "fundamental": ["基本面", "低估值", "价值", "市盈率", "市净率"],
    # PE/PB
    "PE": ["pe", "PE", "市盈率", "估值"],
    "PB": ["pb", "PB", "市净率"],
    # ROE
    "ROE": ["roe", "ROE", "净资产收益率"],
    # RSI
    "RSI": ["rsi", "RSI", "超卖", "超卖反弹"],
    "rsi_oversold": ["rsi超卖", "超卖", "超卖反弹"],
    # KDJ
    "KDJ": ["kdj", "KDJ", "kdj金叉"],
    "kdj_golden": ["kdj金叉", "kdj 金叉"],
    # 突破
    "突破": ["突破", "新高", "突破新高", "创出新高"],
    "breakout": ["突破", "新高", "突破新高", "突破平台"],
}

# 【新增】策略别名映射（扩展）
STRATEGY_ALIASES = {
    "ma_bull": ["均线多头", "ma_bull", "多头排列", "均线排列", "均线向上", "均线趋势", "多头排列"],
    "macd_golden": ["macd金叉", "macd 金叉", "macd", "金叉", "macd交叉", "dif金叉"],
    "rsi_oversold": ["rsi超卖", "rsi 超卖", "rsi", "超卖", "超卖反弹", "rsi反弹"],
    "volume_price": ["量价齐升", "量价", "放量上涨", "量价配合", "量升价涨", "放量", "成交量放大"],
    "breakout": ["突破", "新高", "突破新高", "创出新高", "突破平台", "向上突破"],
    "kdj_golden": ["kdj金叉", "kdj 金叉", "kdj", "kdj交叉", "kdj低位"],
    "fundamental": ["基本面", "低估值", "价值", "pe", "pb", "市盈率", "市净率", "低pe", "低pb"],
}

# 【新增】自然语言意图关键词（扩展）
SELECT_KEYWORDS = ["选股", "选", "找", "筛选", "推荐", "执行", "运行", "找出", "有哪些", "符合", "满足", "个股", "股票", "标的", "挖掘", "挑", "给我看看", "帮我看看", "看看", "帮我找", "帮我选"]
EXPLAIN_KEYWORDS = ["解释", "说明", "什么是", "介绍一下", "怎么理解", "概念", "如何判断", "怎么判断", "什么意思", "原理", "怎么看", "如何识别", "怎么看", "讲讲", "聊一下"]
PRONOUNS = ["这个", "该", "它", "此", "当前", "刚才", "上次", "前面", "之前"]


def detect_strategy(text: str, default: str = None) -> str:
    """从文本中识别策略，支持多别名，返回策略ID或default"""
    for sid, aliases in STRATEGY_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return sid
    return default


def has_pronoun(text: str) -> bool:
    return any(p in text for p in PRONOUNS)


def call_kimi_api(messages: list, temperature: float = 0.3, max_retries: int = 2) -> str:
    """调用 Kimi API，失败返回空字符串"""
    if not MOONSHOT_API_KEY:
        return ""
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {"Authorization": f"Bearer {MOONSHOT_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": KIMI_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == max_retries - 1:
                return ""
    return ""


def parse_intent(user_input: str) -> dict:
    """解析用户意图：Kimi LLM 优先 + 规则引擎 fallback"""
    ctx_strategy = st.session_state.user_pref.get("last_topic", "ma_bull")
    pref_strategy = st.session_state.user_pref.get("strategy", "ma_bull")

    # ========== 【新增】规则引擎：先尝试直接解析组合条件（不依赖LLM）==========
    text = user_input.lower()
    text_orig = user_input  # 保留原始文本用于数值提取

    # 检测是否有"选股/找/筛"等意图词
    has_select_intent = any(k in text for k in SELECT_KEYWORDS)

    # 检测是否包含数值条件（如"小于100亿"、">5%"等）
    # 市值条件
    market_cap_cond = None
    mc_patterns = [
        r"市值\s*(?:小于|低于|<|不超过|≤|<=)\s*([\d.]+)\s*亿",
        r"市值\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)\s*亿",
        r"([\d.]+)\s*亿\s*(?:以下|以内|之内|以下)",
        r"小盘股",  # 特殊：小盘股 = 市值 < 100亿
        r"大盘股",  # 特殊：大盘股 = 市值 > 500亿
    ]
    for pat in mc_patterns:
        m = re.search(pat, text_orig)
        if m:
            if "小盘股" in text_orig:
                market_cap_cond = {"field": "market_cap", "operator": "<", "value": 100, "unit": "亿"}
            elif "大盘股" in text_orig:
                market_cap_cond = {"field": "market_cap", "operator": ">", "value": 500, "unit": "亿"}
            else:
                val = float(m.group(1))
                if any(op in text_orig for op in ["小于", "低于", "不超过", "≤", "<=", "以下", "以内"]):
                    market_cap_cond = {"field": "market_cap", "operator": "<", "value": val, "unit": "亿"}
                elif any(op in text_orig for op in ["大于", "高于", "超过", "≥", ">=", "以上"]):
                    market_cap_cond = {"field": "market_cap", "operator": ">", "value": val, "unit": "亿"}
            break

    # 涨幅条件
    change_cond = None
    chg_patterns = [
        r"涨幅\s*(?:大于|高于|超过|>|≥|>=)\s*([\d.]+)\s*%?",
        r"涨\s*([\d.]+)\s*%\s*(?:以上|以上|以上)",
        r"最近涨得好",  # 特殊：最近涨得好 = 涨幅 > 3%
        r"强势股",  # 特殊：强势股 = 涨幅 > 3% + 换手 > 3%
    ]
    for pat in chg_patterns:
        m = re.search(pat, text_orig)
        if m:
            if "最近涨得好" in text_orig or "强势股" in text_orig:
                change_cond = {"field": "change_pct", "operator": ">", "value": 3, "unit": "%"}
            else:
                val = float(m.group(1))
                change_cond = {"field": "change_pct", "operator": ">", "value": val, "unit": "%"}
            break

    # 股价条件
    price_cond = None
    price_patterns = [
        r"股价\s*(?:小于|低于|<|不超过|≤|<=)\s*([\d.]+)",
        r"股价\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)",
        r"价格\s*(?:小于|低于|<|不超过|≤|<=)\s*([\d.]+)",
        r"价格\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)",
    ]
    for pat in price_patterns:
        m = re.search(pat, text_orig)
        if m:
            val = float(m.group(1))
            if any(op in text_orig for op in ["小于", "低于", "不超过", "≤", "<="]):
                price_cond = {"field": "price", "operator": "<", "value": val, "unit": "元"}
            else:
                price_cond = {"field": "price", "operator": ">", "value": val, "unit": "元"}
            break

    # PE条件
    pe_cond = None
    pe_patterns = [
        r"PE\s*(?:小于|低于|<|不超过|≤|<=)\s*([\d.]+)",
        r"PE\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)",
        r"市盈率\s*(?:小于|低于|<|不超过|≤|<=)\s*([\d.]+)",
        r"市盈率\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)",
        r"低PE",  # 特殊
        r"低估值",  # 特殊
    ]
    for pat in pe_patterns:
        m = re.search(pat, text_orig)
        if m:
            if "低PE" in text_orig or "低估值" in text_orig:
                pe_cond = {"field": "pe", "operator": "<", "value": 30, "unit": ""}
            else:
                val = float(m.group(1))
                if any(op in text_orig for op in ["小于", "低于", "不超过", "≤", "<="]):
                    pe_cond = {"field": "pe", "operator": "<", "value": val, "unit": ""}
                else:
                    pe_cond = {"field": "pe", "operator": ">", "value": val, "unit": ""}
            break

    # 换手率条件
    turnover_cond = None
    turnover_patterns = [
        r"换手\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)\s*%?",
        r"换手率\s*(?:大于|高于|>|超过|≥|>=)\s*([\d.]+)\s*%?",
    ]
    for pat in turnover_patterns:
        m = re.search(pat, text_orig)
        if m:
            val = float(m.group(1))
            turnover_cond = {"field": "turnover", "operator": ">", "value": val, "unit": "%"}
            break

    # ========== 【核心】如果检测到了组合条件，直接返回 select_stocks + 参数 ==========
    nl_params = []
    if market_cap_cond:
        nl_params.append(market_cap_cond)
    if change_cond:
        nl_params.append(change_cond)
    if price_cond:
        nl_params.append(price_cond)
    if pe_cond:
        nl_params.append(pe_cond)
    if turnover_cond:
        nl_params.append(turnover_cond)

    # 如果用户有选股意图，且提取到了至少一个数值条件 → 直接返回组合选股
    if has_select_intent and len(nl_params) >= 1:
        # 构建thought描述
        cond_descs = []
        for c in nl_params:
            cond_descs.append(f"{c['field']}{c['operator']}{c['value']}{c['unit']}")
        thought_str = "用户希望执行自然语言选股：" + ", ".join(cond_descs) + "。"
        
        return {
            "intent": "select_stocks",
            "params": {
                "strategy": "nl_custom",
                "nl_conditions": nl_params,
            },
            "thought": thought_str
        }

    # ========== 原有LLM意图识别逻辑 ==========
    advanced_condition_list = (
        "ma_bull（均线多头排列）, price_above_ma60（股价站上MA60）, macd_golden（MACD金叉）, "
        "macd_positive（日线MACD>0）, macd_quarterly_positive（季线MACD>0）, macd_yearly_positive（年线MACD>0）, "
        "rsi_oversold（RSI超卖反弹）, volume_price（量价齐升）, breakout（突破近期新高）, "
        "kdj_golden（KDJ低位金叉）, fundamental（基本面低估值）, "
        "fundamental_revenue（营业总收入，单位：亿元，可带min参数）, "
        "fundamental_parent_profit（归母净利润，单位：亿元，可带min参数）, "
        "fundamental_deduct_profit（扣非净利润，单位：亿元，可带min参数）, "
        "fundamental_roe（净资产收益率%，可带min参数）, "
        "fundamental_gross_margin（销售毛利率%，可带min参数）, "
        "fundamental_pe（市盈率PE，可带min/max参数）, "
        "fundamental_pb（市净率PB，可带min/max参数）"
    )
    system_prompt = (
        "你是AI选股助手的意图识别模块。请严格按以下JSON格式返回结果，不要任何解释或markdown代码块：\n"
        "{\n"
        '  "intent": "select_stocks|explain_strategy|query_quote|general",\n'
        '  "params": {"strategy": "ma_bull|macd_golden|rsi_oversold|volume_price|breakout|kdj_golden|fundamental|advanced", "code": "6位数字", "conditions": [{"type": "条件ID", "min": 数值}]},\n'
        '  "thought": "简短思考过程"\n'
        "}\n"
        f"当前上下文：用户最近讨论的策略是「{STRATEGY_NAMES.get(ctx_strategy)}」，策略ID为「{ctx_strategy}」。\n"
        "规则：\n"
        "1. select_stocks/explain_strategy 必须在 params.strategy 中返回英文策略ID。\n"
        "2. 当用户要求组合多个条件（如出现'+'、'和'、'并且'、'同时'、'组合'、'多条件'、'高级'等词），strategy 必须返回 advanced，并在 params.conditions 中返回条件对象列表。\n"
        f"3. 高级策略可选条件ID：{advanced_condition_list}。\n"
        "4. 基本面条件必须带阈值参数：营收/净利润单位为亿元，ROE/毛利率单位为%，所有基本面指标均可带 min 和/或 max。"
        "例如营收大于5亿返回 {type:fundamental_revenue,min:5}；营收在3到10亿之间返回 {type:fundamental_revenue,min:3,max:10}；"
        "扣非净利润大于2000万返回 {type:fundamental_deduct_profit,min:0.2}；"
        "ROE在10到30之间返回 {type:fundamental_roe,min:10,max:30}；"
        "PE大于10小于30返回 {type:fundamental_pe,min:10,max:30}；PB小于3返回 {type:fundamental_pb,max:3}。\n"
        "5. 例如'均线多头排列+年线macd和季线macd大于0'应返回 strategy=advanced, conditions=[{type:ma_bull},{type:macd_yearly_positive},{type:macd_quarterly_positive}]。\n"
        "6. query_quote 必须在 params.code 中返回6位股票代码。\n"
        "7. 如果用户输入包含'这个'、'该'、'它'、'此'、'这个指标'、'该策略'等指代词，params.strategy 必须填写上述当前上下文的策略ID，不能为空。\n"
        f"8. 用户偏好策略ID：{pref_strategy}。\n"
        "9. 策略ID映射：均线多头排列→ma_bull，MACD金叉→macd_golden，RSI超卖反弹→rsi_oversold，量价齐升→volume_price，突破近期新高→breakout，KDJ低位金叉→kdj_golden，基本面价值→fundamental。\n"
        "10. 只要包含6位数字，优先考虑 query_quote。"
    )
    llm_resp = call_kimi_api([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ], temperature=0.05)

    if llm_resp:
        try:
            # 提取 JSON 部分（防止 LLM 返回 markdown 代码块）
            json_str = llm_resp
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if parsed.get("intent") in ("select_stocks", "explain_strategy", "query_quote", "general"):
                params = parsed.get("params", {})
                # 解析 strategy
                strategy = params.get("strategy", "")
                if strategy:
                    # 如果是中文，尝试映射
                    if strategy not in STRATEGY_NAMES:
                        mapped = detect_strategy(strategy)
                        if mapped:
                            params["strategy"] = mapped
                        elif has_pronoun(user_input):
                            params["strategy"] = ctx_strategy
                        else:
                            params["strategy"] = pref_strategy
                # 如果 explain/select 没有 strategy，使用上下文或偏好
                if parsed["intent"] in ("select_stocks", "explain_strategy") and not params.get("strategy"):
                    params["strategy"] = ctx_strategy if has_pronoun(user_input) else pref_strategy
                # 解析高级策略条件
                if params.get("strategy") == "advanced" and "conditions" in params:
                    # 规范化 conditions 格式，保留 type 和 min 等参数
                    conds = params["conditions"]
                    if isinstance(conds, list):
                        normalized = []
                        for c in conds:
                            if isinstance(c, dict) and "type" in c:
                                item = {"type": c["type"]}
                                # 保留基本面阈值参数
                                for k in ["min", "max"]:
                                    if k in c:
                                        try:
                                            item[k] = float(c[k])
                                        except (ValueError, TypeError):
                                            item[k] = c[k]
                                normalized.append(item)
                            elif isinstance(c, str):
                                normalized.append({"type": c})
                        params["conditions"] = normalized
                    else:
                        params["conditions"] = []
                # 解析 code/symbol
                code = params.get("code") or params.get("symbol") or ""
                if code:
                    params["code"] = code
                # 补全 thought
                if "thought" not in parsed or not parsed["thought"]:
                    intent = parsed["intent"]
                    if intent == "select_stocks":
                        if params.get("strategy") == "advanced" and params.get("conditions"):
                            names = [ADVANCED_CONDITIONS.get(c.get("type", ""), {}).get("name", c.get("type", "")) for c in params["conditions"]]
                            parsed["thought"] = f"用户希望执行高级策略选股：{' + '.join(names)}。"
                        else:
                            parsed["thought"] = f"用户希望执行「{STRATEGY_NAMES.get(params.get('strategy'), params.get('strategy', ''))}」选股。"
                    elif intent == "explain_strategy":
                        parsed["thought"] = f"用户想了解「{STRATEGY_NAMES.get(params.get('strategy'), params.get('strategy', ''))}」策略。"
                    elif intent == "query_quote":
                        parsed["thought"] = f"用户查询股票代码 {params.get('code')} 的实时行情。"
                    else:
                        parsed["thought"] = "用户进行一般性询问。"
                parsed["params"] = params
                return parsed
        except Exception:
            pass

    # 2. 规则引擎 fallback
    text = user_input.lower()
    result = {"intent": "general", "params": {}, "thought": ""}

    # 解释策略
    if any(k in text for k in EXPLAIN_KEYWORDS):
        strategy = detect_strategy(text, default=ctx_strategy if has_pronoun(text) else None)
        if strategy:
            result["intent"] = "explain_strategy"
            result["params"]["strategy"] = strategy
            result["thought"] = f"用户想深入了解「{STRATEGY_NAMES.get(strategy)}」策略的原理与判断方法。"
            return result
        result["intent"] = "explain_strategy"
        result["params"]["strategy"] = pref_strategy
        result["thought"] = "用户请求解释策略，未明确具体策略，使用用户偏好策略进行说明。"
        return result

    # 选股
    if any(k in text for k in SELECT_KEYWORDS) or "个股" in text or "股票" in text or "标的" in text:
        # 检测是否是组合/高级策略请求
        combo_markers = ["+", "，", ",", "和", "并且", "同时", "组合", "多条件", "高级"]
        is_combo = any(m in user_input for m in combo_markers) or "多策略" in user_input
        if is_combo:
            # 尝试提取多个条件
            from strategies import ADVANCED_CONDITIONS
            matched = []
            for cond_id, meta in ADVANCED_CONDITIONS.items():
                # 简单匹配：条件名称或别名是否出现在文本中
                if meta["name"] in user_input or cond_id in user_input:
                    matched.append({"type": cond_id})
                else:
                    # 额外别名匹配
                    aliases = {
                        "ma_bull": ["均线多头", "多头排列"],
                        "macd_positive": ["macd大于0", "macd>0", "macd 大于 0"],
                        "macd_quarterly_positive": ["季线macd", "季度macd", "季macd"],
                        "macd_yearly_positive": ["年线macd", "年度macd", "年macd"],
                        "fundamental_revenue": ["营收", "营业收入", "营业总收入"],
                        "fundamental_parent_profit": ["归母净利润", "归母净利"],
                        "fundamental_deduct_profit": ["扣非净利润", "扣非净利", "扣非"],
                        "fundamental_roe": ["roe", "净资产收益率"],
                        "fundamental_gross_margin": ["毛利率", "销售毛利率"],
                        "fundamental_pe": ["市盈率", "pe"],
                        "fundamental_pb": ["市净率", "pb"],
                    }
                    if any(a in text for a in aliases.get(cond_id, [])):
                        matched.append({"type": cond_id})
            # 尝试为基本面条件提取阈值（支持范围与单边界）
            for item in matched:
                cid = item["type"]
                if cid == "fundamental_revenue":
                    range_m = re.search(r"(?:营收|营业总收入).*?([\d.]+)\s*[-~到至]\s*([\d.]+)\s*亿", user_input)
                    if range_m:
                        item["min"] = float(range_m.group(1))
                        item["max"] = float(range_m.group(2))
                    else:
                        m = re.search(r"(?:营收|营业总收入).*?(?:大于|>=|>)\s*([\d.]+)\s*亿", user_input)
                        if m:
                            item["min"] = float(m.group(1))
                        m = re.search(r"(?:营收|营业总收入).*?(?:小于|<=|<)\s*([\d.]+)\s*亿", user_input)
                        if m:
                            item["max"] = float(m.group(1))
                elif cid in ("fundamental_parent_profit", "fundamental_deduct_profit"):
                    profit_name = "归母净利润" if cid == "fundamental_parent_profit" else "扣非净利润"
                    range_m = re.search(rf"{profit_name}.*?([\d.]+)\s*[-~到至]\s*([\d.]+)\s*(万|亿)", user_input)
                    if range_m:
                        def _to_yi(v, u):
                            return float(v) / 10000 if u == "万" else float(v)
                        item["min"] = _to_yi(range_m.group(1), range_m.group(3))
                        item["max"] = _to_yi(range_m.group(2), range_m.group(3))
                    else:
                        m = re.search(rf"{profit_name}.*?([\d.]+)\s*万", user_input)
                        if m:
                            item["min"] = float(m.group(1)) / 10000
                        else:
                            m = re.search(rf"{profit_name}.*?([\d.]+)\s*亿", user_input)
                            if m:
                                item["min"] = float(m.group(1))
                        m = re.search(rf"{profit_name}.*?(?:小于|<=|<)\s*([\d.]+)\s*亿", user_input)
                        if m:
                            item["max"] = float(m.group(1))
                elif cid == "fundamental_roe":
                    range_m = re.search(r"(?:roe|净资产收益率).*?([\d.]+)\s*[-~到至]\s*([\d.]+)", text)
                    if range_m:
                        item["min"] = float(range_m.group(1))
                        item["max"] = float(range_m.group(2))
                    else:
                        m = re.search(r"(?:roe|净资产收益率).*?(?:大于|>=|>)\s*([\d.]+)", text)
                        if m:
                            item["min"] = float(m.group(1))
                        m = re.search(r"(?:roe|净资产收益率).*?(?:小于|<=|<)\s*([\d.]+)", text)
                        if m:
                            item["max"] = float(m.group(1))
                elif cid == "fundamental_gross_margin":
                    range_m = re.search(r"(?:毛利率|销售毛利率).*?([\d.]+)\s*[-~到至]\s*([\d.]+)", user_input)
                    if range_m:
                        item["min"] = float(range_m.group(1))
                        item["max"] = float(range_m.group(2))
                    else:
                        m = re.search(r"(?:毛利率|销售毛利率).*?(?:大于|>=|>)\s*([\d.]+)", user_input)
                        if m:
                            item["min"] = float(m.group(1))
                        m = re.search(r"(?:毛利率|销售毛利率).*?(?:小于|<=|<)\s*([\d.]+)", user_input)
                        if m:
                            item["max"] = float(m.group(1))
                elif cid == "fundamental_pe":
                    # 支持 "PE在10到30之间" / "PE大于10小于30" / "PE<30"
                    range_m = re.search(r"(?:pe|市盈率).*?([\d.]+)\s*[-~到至]\s*([\d.]+)", text)
                    if range_m:
                        item["min"] = float(range_m.group(1))
                        item["max"] = float(range_m.group(2))
                    else:
                        m_min = re.search(r"(?:pe|市盈率).*?(?:大于|>=|>)", text)
                        m_max = re.search(r"(?:pe|市盈率).*?(?:小于|<=|<)", text)
                        if m_min:
                            num_m = re.search(r"(?:pe|市盈率).*?(?:大于|>=|>)\s*([\d.]+)", text)
                            if num_m:
                                item["min"] = float(num_m.group(1))
                        if m_max:
                            num_m = re.search(r"(?:pe|市盈率).*?(?:小于|<=|<)\s*([\d.]+)", text)
                            if num_m:
                                item["max"] = float(num_m.group(1))
                elif cid == "fundamental_pb":
                    range_m = re.search(r"(?:pb|市净率).*?([\d.]+)\s*[-~到至]\s*([\d.]+)", text)
                    if range_m:
                        item["min"] = float(range_m.group(1))
                        item["max"] = float(range_m.group(2))
                    else:
                        m_min = re.search(r"(?:pb|市净率).*?(?:大于|>=|>)", text)
                        m_max = re.search(r"(?:pb|市净率).*?(?:小于|<=|<)", text)
                        if m_min:
                            num_m = re.search(r"(?:pb|市净率).*?(?:大于|>=|>)\s*([\d.]+)", text)
                            if num_m:
                                item["min"] = float(num_m.group(1))
                        if m_max:
                            num_m = re.search(r"(?:pb|市净率).*?(?:小于|<=|<)\s*([\d.]+)", text)
                            if num_m:
                                item["max"] = float(num_m.group(1))
            if len(matched) >= 2 or (len(matched) == 1 and any("fundamental" in c["type"] for c in matched)):
                result["intent"] = "select_stocks"
                result["params"]["strategy"] = "advanced"
                result["params"]["conditions"] = matched
                names = [ADVANCED_CONDITIONS.get(c["type"], {}).get("name", c["type"]) for c in matched]
                result["thought"] = f"用户希望执行高级策略选股：{' + '.join(names)}。"
                return result

        strategy = detect_strategy(text, default=ctx_strategy if has_pronoun(text) else None)
        if strategy:
            result["intent"] = "select_stocks"
            result["params"]["strategy"] = strategy
            result["thought"] = f"用户希望找出符合「{STRATEGY_NAMES.get(strategy)}」策略的个股。"
            return result

    # 查询个股行情（修复中文边界问题）
    code_match = re.search(r"(?:^|\D)(\d{6})(?:$|\D)", user_input)
    if code_match:
        result["intent"] = "query_quote"
        result["params"]["code"] = code_match.group(1)
        result["thought"] = f"用户查询股票代码 {result['params']['code']} 的实时行情。"
        return result

    result["thought"] = "未匹配到明确的选股/解释/行情意图，作为一般对话处理。"
    return result


def execute_action(intent: str, params: dict) -> dict:
    """执行 ReAct 的 Action，返回 Observation"""
    obs = {"ok": True, "data": "", "type": "text"}
    if intent == "select_stocks":
        strategy = params.get("strategy", "ma_bull")
        st.session_state.user_pref["strategy"] = strategy
        st.session_state.user_pref["last_topic"] = strategy
        # 删除 nav_radio 的 widget 状态，让 sidebar radio 在 rerun 时读取新的 index
        if "nav_radio" in st.session_state:
            del st.session_state.nav_radio
        st.session_state.current_page = "📈 策略选股"
        st.session_state.run_trigger = True
        st.session_state.agent_target_strategy = strategy
        
        # 【新增】处理自然语言自定义选股
        if strategy == "nl_custom" and params.get("nl_conditions"):
            st.session_state.agent_nl_conditions = params["nl_conditions"]
            obs["data"] = f"已识别自然语言选股条件，正在为您筛选符合条件的股票..."
            obs["type"] = "navigate"
            return obs
        
        # 高级策略：保存条件列表（保留 type/min 等参数）
        if strategy == "advanced" and params.get("conditions"):
            st.session_state.agent_advanced_conditions = [
                {k: v for k, v in c.items() if k in ("type", "min", "max")}
                for c in params["conditions"] if isinstance(c, dict) and c.get("type")
            ]
            st.session_state.agent_advanced_mode = True
        obs["data"] = f"已切换到「{STRATEGY_NAMES.get(strategy, strategy)}」策略并触发选股。"
        obs["type"] = "navigate"
    elif intent == "query_quote":
        code = params.get("code", "")
        try:
            df = get_realtime_quotes([code])
            if not df.empty:
                r = df.iloc[0]
                obs["data"] = f"{r.get('名称', code)}（{code}）最新价 ¥{r.get('最新价', 'N/A')}，涨跌幅 {r.get('涨跌幅', 0):+.2f}%，成交量 {r.get('成交量', 0):,.0f}。"
            else:
                obs["data"] = f"未查询到 {code} 的行情数据。"
        except Exception as e:
            obs["data"] = f"查询失败：{e}"
            obs["ok"] = False
    elif intent == "explain_strategy":
        strategy = params.get("strategy", "ma_bull")
        st.session_state.user_pref["last_topic"] = strategy
        data = STRATEGY_DETAIL_DATA.get(strategy, {})
        desc = data.get("desc", "暂无说明")
        conds = "\n".join([f"• **{c[0]}**：{c[1]}\n  💡 {c[2]}" for c in data.get("strategy_conditions", [])])
        filters = "\n".join([f"• {c[0]}：{c[1]}" for c in data.get("global_filters", [])])
        obs["data"] = (
            f"**{STRATEGY_NAMES.get(strategy, strategy)}**\n\n{desc}\n\n"
            f"**策略选股条件：**\n{conds}\n\n"
            f"**全局过滤条件：**\n{filters}\n\n"
            f"您可以直接说「找到现在符合这个指标的个股」，我会用该策略为您选股。"
        )
    else:
        # 更友好的默认回复，根据上下文给出引导
        ctx_strategy = st.session_state.user_pref.get("last_topic")
        if ctx_strategy:
            obs["data"] = (
                f"我注意到咱们刚才在聊「{STRATEGY_NAMES.get(ctx_strategy)}」策略。\n\n"
                f"您可以这样继续：\n"
                f"• 「找到现在符合这个指标的个股」→ 执行选股\n"
                f"• 「解释一下这个策略」→ 查看策略原理\n"
                f"• 「000988 怎么样」→ 查询个股行情"
            )
        else:
            obs["data"] = (
                "我是您的 AI 选股助手，可以帮您：\n"
                "• 执行选股：「用均线多头排列选股」\n"
                "• 解释策略：「解释量价齐升」\n"
                "• 查询行情：「000988 怎么样」\n\n"
                "请告诉我您想了解什么？"
            )
    return obs


def generate_response(thought: str, observation: dict, user_input: str) -> str:
    """生成 ReAct 的最终回答，使用 Kimi LLM 润色"""
    if observation["type"] == "navigate":
        return f"🧠 **思考**：{thought}\n\n🛠️ **行动**：{observation['data']}\n\n👉 已为您跳转至策略选股页面，正在执行分析，请稍候..."

    # 使用 Kimi LLM 润色为非 navigate 回答生成更自然的回复
    system_prompt = (
        "你是AI选股助手。请根据用户的原始问题、Agent的思考过程和执行结果，"
        "生成一段自然、友好、专业的中文回复。要求：\n"
        "1. 不要重复'思考'过程，直接给出结论；\n"
        "2. 如果是策略解释，分点说明并给出判断方法；\n"
        "3. 如果是行情数据，直接报出关键数字；\n"
        "4. 如果执行了选股，告诉用户已触发选股并请查看策略选股页面；\n"
        "5. 保持简洁，控制在200字以内。"
    )
    prompt = f"用户问题：{user_input}\nAgent思考：{thought}\n执行结果：{observation['data']}\n\n请生成最终回复："
    polished = call_kimi_api([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ], temperature=0.4)

    if polished:
        return polished
    return f"🧠 **思考**：{thought}\n\n🔍 **结果**：\n\n{observation['data']}"


def run_agent_self_check() -> list:
    """自动运行 5 个测试用例，验证 Agent 意图识别是否正确"""
    # 预设上下文：用户刚问过量价齐升
    original_topic = st.session_state.user_pref.get("last_topic")
    st.session_state.user_pref["last_topic"] = "volume_price"

    test_cases = [
        ("解释量价齐升", "explain_strategy", {}),
        ("000988怎么样", "query_quote", {"code": "000988"}),
        ("用均线多头排列选股", "select_stocks", {"strategy": "ma_bull"}),
        ("什么是MACD金叉", "explain_strategy", {"strategy": "macd_golden"}),
        ("找到现在符合这个指标的个股", "select_stocks", {"strategy": "volume_price"}),
    ]

    results = []
    for q, expected, expected_params in test_cases:
        try:
            parsed = parse_intent(q)
            actual = parsed.get("intent", "general")
            params = parsed.get("params", {})
            ok = (actual == expected)
            # 参数校验
            for k, v in expected_params.items():
                if params.get(k) != v:
                    ok = False
                    break
            results.append({
                "question": q,
                "expected": expected,
                "actual": actual,
                "params": params,
                "ok": ok,
                "thought": parsed.get("thought", "")
            })
        except Exception as e:
            results.append({
                "question": q,
                "expected": expected,
                "actual": f"ERROR: {e}",
                "params": {},
                "ok": False,
                "thought": ""
            })

    # 恢复原始上下文
    if original_topic:
        st.session_state.user_pref["last_topic"] = original_topic
    return results


def render_home_page():
    """首页"""
    st.title("🤖 AI选股系统")
    st.markdown("""
    <div style="font-size:16px;color:#555;line-height:1.8;">
    基于实时行情数据，结合多种技术分析策略，帮助您发现潜在投资机会。<br>
    新增 <b>AI 选股助手</b>，可通过自然语言对话执行选股、查询行情、解释策略。
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🤖 进入 AI 选股助手", type="primary", width="stretch"):
            if "nav_radio" in st.session_state:
                del st.session_state.nav_radio
            st.session_state.current_page = "🤖 AI选股助手"
            st.rerun()
    with c2:
        if st.button("📈 进入策略选股", type="secondary", width="stretch"):
            if "nav_radio" in st.session_state:
                del st.session_state.nav_radio
            st.session_state.current_page = "📈 策略选股"
            st.rerun()

    st.divider()
    st.subheader("📊 快速概览")
    if "last_result" in st.session_state and st.session_state.last_result is not None:
        last = st.session_state.last_result
        strategy = STRATEGY_NAMES.get(st.session_state.get("last_strategy", ""), "")
        st.info(f"上次选股结果：{strategy} 策略，共选出 **{len(last)}** 只股票。")
    else:
        st.info("暂无选股记录，点击上方按钮开始分析。")

    st.caption("⚠️ 本系统仅供学习研究，不构成投资建议。")


def render_agent_page():
    """AI 选股助手页面"""
    st.title("🤖 AI 选股助手")
    st.caption("基于 ReAct 框架：先思考 → 再行动 → 最后回答")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("请输入您的问题，例如：帮我用均线多头排列策略选股 / 000988 怎么样 / 解释 MACD金叉")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        try:
            with st.chat_message("assistant"):
                with st.status("🧠 正在思考...", expanded=True) as status:
                    parsed = parse_intent(user_input)
                    st.markdown(f"**意图识别：** {parsed['thought']}")
                    st.markdown(f"**执行行动：** `{parsed['intent']}`")
                    observation = execute_action(parsed["intent"], parsed["params"])
                    st.markdown(f"**观察结果：** {observation['data'][:200]}...")
                    status.update(label="✅ 思考完成", state="complete", expanded=False)

                final = generate_response(parsed["thought"], observation, user_input)
                st.markdown(final)
                st.session_state.chat_history.append({"role": "assistant", "content": final})

            if observation.get("type") == "navigate":
                st.rerun()
        except Exception as e:
            error_msg = (
                f"抱歉，处理您的请求时遇到了问题：{e}\n\n"
                "我可以帮您：\n"
                "• 解释某个策略（如：解释量价齐升）\n"
                "• 查询个股行情（如：000988 怎么样）\n"
                "• 执行选股（如：用均线多头排列选股）\n\n"
                "请换一种方式描述您的需求。"
            )
            st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
            with st.chat_message("assistant"):
                st.markdown(error_msg)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🧪 自动测试", width="stretch"):
            with st.status("🧪 正在自动运行 5 个测试用例...", expanded=True) as status:
                results = run_agent_self_check()
                status.update(label="✅ 测试完成", state="complete", expanded=True)
            for r in results:
                icon = "✅" if r["ok"] else "❌"
                st.markdown(f"{icon} **{r['question']}** → 期望 `{r['expected']}` / 实际 `{r['actual']}`")
                if r["params"]:
                    st.caption(f"参数：{r['params']}")
            passed = sum(1 for r in results if r["ok"])
            if passed == len(results):
                st.success(f"🎉 全部 {len(results)} 个测试用例通过！")
            else:
                st.warning(f"⚠️ {passed}/{len(results)} 个测试用例通过，请检查失败项。")
    with c2:
        if st.button("🗑️ 清空对话", width="stretch"):
            st.session_state.chat_history = []
            st.rerun()

# ========== 侧边栏（全部选股条件） ==========
with st.sidebar:
    st.header("⚙️ 配置中心")
    # 页面导航
    page = st.radio("页面导航", ["🏠 首页", "🤖 AI选股助手", "📈 策略选股"],
                    index=["🏠 首页", "🤖 AI选股助手", "📈 策略选股"].index(st.session_state.current_page),
                    key="nav_radio")
    if page != st.session_state.current_page:
        st.session_state.current_page = page
        st.rerun()
    st.divider()

    strategy_keys = list(STRATEGY_NAMES.keys())
    # 处理 AI 助手传来的策略目标（在 selectbox 实例化前设置默认值）
    if "agent_target_strategy" in st.session_state:
        target = st.session_state.agent_target_strategy
        if target in strategy_keys:
            st.session_state.sb_strategy = target
        del st.session_state.agent_target_strategy

    # 高级策略模式开关
    if "advanced_mode" not in st.session_state:
        st.session_state.advanced_mode = False
    # AI 助手触发高级策略时，重置 toggle 状态
    if "agent_advanced_mode" in st.session_state:
        st.session_state.advanced_mode = st.session_state.agent_advanced_mode
        if "adv_mode_toggle" in st.session_state:
            del st.session_state.adv_mode_toggle
        del st.session_state.agent_advanced_mode
    advanced_mode = st.toggle("🔧 高级策略模式（多条件组合）", value=st.session_state.advanced_mode, key="adv_mode_toggle")

    if advanced_mode:
        # AI 助手传来的高级条件
        if "agent_advanced_conditions" in st.session_state:
            st.session_state.advanced_conditions = st.session_state.agent_advanced_conditions
            del st.session_state.agent_advanced_conditions

        if "advanced_conditions" not in st.session_state:
            st.session_state.advanced_conditions = []

        # 规范化：从 AI 助手传入的可能是 dict 列表，也可能是 str 列表
        raw_conds = st.session_state.advanced_conditions
        cond_map = {}
        for c in raw_conds:
            if isinstance(c, dict):
                cond_map[c.get("type", "")] = c
            elif isinstance(c, str):
                cond_map[c] = {"type": c}

        st.markdown("**📋 选择要组合的策略条件（取交集）**")
        from strategies import ADVANCED_CONDITIONS
        selected = []
        for cond_id, meta in ADVANCED_CONDITIONS.items():
            default = cond_id in cond_map
            if st.checkbox(f"{meta['name']}", value=default, help=meta["desc"], key=f"adv_cond_{cond_id}"):
                selected.append(cond_map.get(cond_id, {"type": cond_id}))
        st.session_state.advanced_conditions = selected
        sel_strategy = "advanced"

        # 高级策略详情
        with st.expander("📖 已选条件说明", expanded=True):
            if selected:
                for c in selected:
                    cid = c.get("type", "")
                    meta = ADVANCED_CONDITIONS.get(cid, {})
                    detail = f"min={c['min']}" if "min" in c else meta.get("desc", "")
                    st.markdown(f"✓ **{meta.get('name', cid)}** — {detail}")
            else:
                st.caption("请至少选择一个条件")
    else:
        sel_strategy = st.selectbox(
            "选股策略", options=strategy_keys,
            format_func=lambda x: STRATEGY_NAMES[x], key="sb_strategy"
        )

        # 策略详情（纯Streamlit组件，避免HTML渲染问题）
        detail = STRATEGY_DETAIL_DATA.get(sel_strategy, {})
        if detail:
            with st.expander(f"📖 查看「{STRATEGY_NAMES.get(sel_strategy, '')}」策略详情", expanded=True):
                st.caption(detail.get("desc", ""))

                st.markdown("**📌 策略选股条件**")
                for cond_text, plain, tip in detail.get("strategy_conditions", []):
                    st.markdown(f"✓ **{cond_text}** — *{plain}*")
                    st.caption(f"💡 {tip}")

                st.caption("该解释基于您设定的策略条件自动生成")

    st.divider()

    # 全局过滤条件
    st.subheader("🔧 全局过滤")
    filter_st = st.toggle("🚫 排除ST/退市/风险股", value=True)
    filter_hs = st.toggle("🇨🇳 仅沪深A股", value=True)

    c1, c2 = st.columns(2)
    with c1:
        min_price = st.number_input("最低价格", value=2.0, min_value=0.1, step=1.0, format="%.2f", key="f_min_price")
    with c2:
        max_price = st.number_input("最高价格", value=500.0, min_value=1.0, step=10.0, format="%.2f", key="f_max_price")

    c1, c2 = st.columns(2)
    with c1:
        chg_min = st.number_input("最小涨跌%", value=-10.0, min_value=-20.0, max_value=20.0, step=0.5, key="f_chg_min")
    with c2:
        chg_max = st.number_input("最大涨跌%", value=10.0, min_value=-20.0, max_value=20.0, step=0.5, key="f_chg_max")

    c1, c2 = st.columns(2)
    with c1:
        vol_min = st.number_input("最小成交量(万手)", value=0, min_value=0, step=100, key="f_vol_min")
    with c2:
        vol_max = st.number_input("最大成交量(万手)", value=100000, min_value=0, step=1000, key="f_vol_max")

    c1, c2 = st.columns(2)
    with c1:
        pe_min = st.number_input("最小PE", value=0.0, min_value=0.0, step=1.0, key="f_pe_min")
    with c2:
        pe_max = st.number_input("最大PE", value=500.0, min_value=0.0, step=10.0, key="f_pe_max")

    c1, c2 = st.columns(2)
    with c1:
        pb_min = st.number_input("最小PB", value=0.0, min_value=0.0, step=0.1, key="f_pb_min")
    with c2:
        pb_max = st.number_input("最大PB", value=50.0, min_value=0.0, step=1.0, key="f_pb_max")

    st.divider()

    # 策略参数
    st.subheader("📋 策略参数")
    extra = {}
    if sel_strategy == "rsi_oversold":
        extra["rsi_low"] = st.slider("RSI超卖线", 10, 40, 30, key="p_rsi_low")
        extra["rsi_high"] = st.slider("RSI反弹上限", 20, 60, 45, key="p_rsi_high")
    elif sel_strategy == "breakout":
        extra["days"] = st.slider("突破周期(日)", 20, 120, 60, key="p_days")
    elif sel_strategy == "fundamental":
        extra["max_pe"] = st.slider("最大PE", 5, 100, 30, key="p_max_pe")
        extra["max_pb"] = st.slider("最大PB", 0.5, 10.0, 3.0, 0.5, key="p_max_pb")
    elif sel_strategy == "advanced":
        # 高级策略参数（仅当对应条件被选中时才显示）
        selected = st.session_state.get("advanced_conditions", [])
        if "rsi_oversold" in selected:
            extra["rsi_low"] = st.slider("RSI超卖线", 10, 40, 30, key="p_adv_rsi_low")
            extra["rsi_high"] = st.slider("RSI反弹上限", 20, 60, 45, key="p_adv_rsi_high")
        if "breakout" in selected:
            extra["breakout_days"] = st.slider("突破周期(日)", 20, 120, 60, key="p_adv_breakout_days")
        if "fundamental" in selected:
            extra["max_pe"] = st.slider("最大PE", 5, 100, 30, key="p_adv_max_pe")
            extra["max_pb"] = st.slider("最大PB", 0.5, 10.0, 3.0, 0.5, key="p_adv_max_pb")
        # 基本面专业指标阈值（统一放在可展开区域）
        # 格式: (标签, 最小允许值, 最大允许值, 默认最小值, 默认最大值, key前缀)
        fundamental_all = {
            "fundamental_revenue": ("营业总收入（亿元）", 0.0, 100000.0, 3.0, 100000.0, "revenue"),
            "fundamental_parent_profit": ("归母净利润（亿元）", 0.0, 100000.0, 0.2, 100000.0, "parent_profit"),
            "fundamental_deduct_profit": ("扣非净利润（亿元）", 0.0, 100000.0, 0.2, 100000.0, "deduct_profit"),
            "fundamental_roe": ("净资产收益率（%）", 0.0, 1000.0, 5.0, 1000.0, "roe"),
            "fundamental_gross_margin": ("销售毛利率（%）", 0.0, 100.0, 20.0, 100.0, "gross_margin"),
            "fundamental_pe": ("市盈率PE", 0.0, 1000.0, 0.0, 500.0, "pe"),
            "fundamental_pb": ("市净率PB", 0.0, 100.0, 0.0, 50.0, "pb"),
        }
        selected_types = {c.get("type", "") if isinstance(c, dict) else c for c in selected}
        has_fundamental = any(c in selected_types for c in fundamental_all)
        if has_fundamental:
            with st.expander("📊 基本面筛选阈值", expanded=True):
                for cond_id, (label, min_v, max_v, def_min, def_max, key_prefix) in fundamental_all.items():
                    if cond_id in selected_types:
                        c1, c2 = st.columns(2)
                        extra[f"{key_prefix}_min"] = c1.number_input(
                            f"最小{label}", value=def_min, min_value=min_v, max_value=max_v, step=0.1,
                            key=f"p_adv_{key_prefix}_min"
                        )
                        extra[f"{key_prefix}_max"] = c2.number_input(
                            f"最大{label}", value=def_max, min_value=min_v, max_value=max_v, step=0.1,
                            key=f"p_adv_{key_prefix}_max"
                        )
        if not selected:
            st.caption("请在上方选择至少一个条件")
    else:
        st.caption("当前策略无额外参数")

    st.divider()

    # 性能设置
    st.subheader("⚡ 性能设置")
    max_candidates = st.slider(
        "候选股上限", 100, 2000,
        st.session_state.max_candidates, 100,
        help="技术分析策略仅分析换手率最高的N只",
        key="slider_max_cand"
    )
    st.session_state.max_candidates = max_candidates

    st.divider()

    # 执行按钮
    btn_label = "🚀 执行高级选股" if sel_strategy == "advanced" else "🚀 执行选股"
    run_clicked = st.button(btn_label, type="primary", width="stretch", key="btn_run")
    st.caption("⚠️ AI基于历史数据筛选，结果不代表未来表现。")

# ========== 概览卡片 ==========
# 过滤后的股票池大小
# 【修复】增加空数据保护
try:
    if stock_list.empty or "名称" not in stock_list.columns:
        st.error(f"⚠️ 股票列表加载失败：数据为空或缺少'名称'列。列名：{list(stock_list.columns)}")
        st.stop()
except Exception as e:
    st.error(f"⚠️ 股票列表加载异常：{str(e)}")
    st.stop()

if filter_st:
    stock_list_filtered = stock_list[~stock_list["名称"].apply(is_risk_stock)]
else:
    stock_list_filtered = stock_list.copy()

if filter_hs:
    stock_list_filtered = stock_list_filtered[stock_list_filtered["代码"].apply(is_hs_stock)]

pool_size = len(stock_list_filtered)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("股票池", f"{pool_size}只")
with col2:
    st.metric("策略数", f"{len(STRATEGIES)}种")
with col3:
    st.metric("数据源", "腾讯实时")
with col4:
        if sel_strategy == "fundamental":
            st.metric("分析方式", "全量")
        elif sel_strategy == "advanced":
            st.metric("分析方式", "高级组合")
        else:
            st.metric("候选上限", f"{max_candidates}只")
with col5:
    st.metric("状态", "🟢 在线")

st.divider()

# ========== 页面路由 ==========
if st.session_state.current_page == "🏠 首页":
    render_home_page()
    st.stop()
elif st.session_state.current_page == "🤖 AI选股助手":
    render_agent_page()
    st.stop()

# ========== 选股执行 ==========
if run_clicked:
    st.session_state.run_trigger = True

if st.session_state.get("run_trigger", False):
    st.session_state.run_trigger = False

    need_kline = sel_strategy != "fundamental"

    with st.status("📡 正在获取实时行情...", expanded=True) as status:
        all_codes = stock_list_filtered["代码"].tolist()
        all_quotes = get_realtime_quotes(all_codes)
        # 避免merge时名称列冲突，先删除quotes中的名称列
        if "名称" in all_quotes.columns:
            all_quotes = all_quotes.drop(columns=["名称"])
        # 【修复】确保代码列类型一致（str）
        stock_list_filtered["代码"] = stock_list_filtered["代码"].astype(str)
        if not all_quotes.empty:
            all_quotes["代码"] = all_quotes["代码"].astype(str)
        merged = stock_list_filtered.merge(all_quotes, on="代码", how="inner")
        status.update(label=f"✅ 实时行情获取完成 ({len(merged)}只)")

    # 价格过滤
    final_min = min(min_price, max_price)
    final_max = max(min_price, max_price)
    merged = merged[(merged["最新价"] >= final_min) & (merged["最新价"] <= final_max)]

    # 涨跌幅过滤
    if chg_min is not None and chg_max is not None:
        cmin, cmax = min(chg_min, chg_max), max(chg_min, chg_max)
        merged = merged[(merged["涨跌幅"] >= cmin) & (merged["涨跌幅"] <= cmax)]

    # 成交量过滤
    if vol_min is not None and vol_max is not None:
        vmin, vmax = min(vol_min, vol_max), max(vol_min, vol_max)
        merged = merged[(merged["成交量"] >= vmin * 10000) & (merged["成交量"] <= vmax * 10000)]

    # PE过滤
    if pe_min is not None and pe_max is not None:
        pmin, pmax = min(pe_min, pe_max), max(pe_min, pe_max)
        merged = merged[(merged["市盈率"] >= pmin) & (merged["市盈率"] <= pmax)]

    # PB过滤
    if pb_min is not None and pb_max is not None:
        bmin, bmax = min(pb_min, pb_max), max(pb_min, pb_max)
        merged = merged[(merged["市净率"] >= bmin) & (merged["市净率"] <= bmax)]

    if merged.empty:
        st.warning("⚠️ 过滤后没有符合条件的股票，请放宽过滤条件。")
        st.stop()

    # 候选股截断（仅技术分析策略）
    truncated = False
    if need_kline and len(merged) > max_candidates:
        merged = merged.sort_values("换手率", ascending=False).head(max_candidates).reset_index(drop=True)
        truncated = True

    analysis_pool = merged

    # 获取K线
    klines_dict = {}
    if need_kline:
        prog = st.progress(0, text="正在批量获取K线数据...")
        try:
            k_days = 250 if sel_strategy == "advanced" else 120
            klines_dict = batch_get_klines(
                analysis_pool["代码"].tolist(), days=k_days,
                progress_callback=lambda completed, total: prog.progress(min(completed/total, 0.99))
            )
        except Exception as e:
            st.error(f"获取K线失败: {e}")
            st.stop()
        finally:
            prog.empty()

    # ========== 【新增】自然语言自定义选股过滤 ==========
    if sel_strategy == "nl_custom" and "agent_nl_conditions" in st.session_state:
        nl_conds = st.session_state.agent_nl_conditions
        with st.status("🧠 正在应用自然语言条件...", expanded=True) as nl_status:
            for cond in nl_conds:
                field = cond.get("field", "")
                op = cond.get("operator", "")
                val = cond.get("value", 0)
                unit = cond.get("unit", "")
                
                st.write(f"应用条件: {field} {op} {val}{unit}")
                
                if field == "market_cap":
                    # 市值过滤：从 stock_list_filtered 中获取市值数据
                    # 注意：腾讯实时API可能没有直接返回市值，需要从基本面数据获取
                    if "总市值" not in analysis_pool.columns:
                        # 尝试获取基本面数据
                        try:
                            fin_report = get_financial_report()
                            if not fin_report.empty and "总市值" in fin_report.columns:
                                analysis_pool = analysis_pool.merge(fin_report[["代码", "总市值"]], on="代码", how="left")
                        except:
                            pass
                    if "总市值" in analysis_pool.columns:
                        analysis_pool["总市值"] = pd.to_numeric(analysis_pool["总市值"], errors="coerce")
                        if op == "<":
                            analysis_pool = analysis_pool[analysis_pool["总市值"] < val]
                        elif op == ">":
                            analysis_pool = analysis_pool[analysis_pool["总市值"] > val]
                
                elif field == "change_pct":
                    # 涨幅过滤
                    analysis_pool["涨跌幅"] = pd.to_numeric(analysis_pool["涨跌幅"], errors="coerce")
                    if op == ">":
                        analysis_pool = analysis_pool[analysis_pool["涨跌幅"] > val]
                    elif op == "<":
                        analysis_pool = analysis_pool[analysis_pool["涨跌幅"] < val]
                
                elif field == "price":
                    # 股价过滤（已在全局过滤中处理，但这里可以更精确）
                    analysis_pool["最新价"] = pd.to_numeric(analysis_pool["最新价"], errors="coerce")
                    if op == "<":
                        analysis_pool = analysis_pool[analysis_pool["最新价"] < val]
                    elif op == ">":
                        analysis_pool = analysis_pool[analysis_pool["最新价"] > val]
                
                elif field == "pe":
                    # PE过滤
                    analysis_pool["市盈率"] = pd.to_numeric(analysis_pool["市盈率"], errors="coerce")
                    if op == "<":
                        analysis_pool = analysis_pool[analysis_pool["市盈率"] < val]
                    elif op == ">":
                        analysis_pool = analysis_pool[analysis_pool["市盈率"] > val]
                
                elif field == "turnover":
                    # 换手率过滤
                    analysis_pool["换手率"] = pd.to_numeric(analysis_pool["换手率"], errors="coerce")
                    if op == ">":
                        analysis_pool = analysis_pool[analysis_pool["换手率"] > val]
                    elif op == "<":
                        analysis_pool = analysis_pool[analysis_pool["换手率"] < val]
            
            nl_status.update(label=f"✅ 自然语言条件过滤完成，剩余 {len(analysis_pool)} 只股票", state="complete", expanded=False)
        
        # 清除自然语言条件，避免重复应用
        del st.session_state.agent_nl_conditions
        
        # 自然语言选股结果直接返回
        result = analysis_pool.copy()
        
        # 补充实时行情列
        if not result.empty and "涨跌幅" not in result.columns and "涨跌幅" in analysis_pool.columns:
            extra_cols = [c for c in ["涨跌幅", "成交量", "换手率", "市盈率", "市净率"] if c in analysis_pool.columns and c not in result.columns]
            if extra_cols:
                merge_cols = ["代码"] + extra_cols
                result = result.merge(analysis_pool[merge_cols], on="代码", how="left")
    
    else:
        # 执行原有策略
        func = STRATEGIES[sel_strategy]
        try:
            if sel_strategy == "fundamental":
                result = func(analysis_pool, **extra)
            elif sel_strategy == "advanced":
                conditions = st.session_state.get("advanced_conditions", [])
                # 规范化 conditions
                normalized = []
                for c in conditions:
                    if isinstance(c, dict) and c.get("type"):
                        normalized.append(c)
                    elif isinstance(c, str):
                        normalized.append({"type": c})
                conditions = normalized
                if not conditions:
                    st.warning("⚠️ 请先在侧边栏选择至少一个高级策略条件。")
                    st.stop()
                # 如果包含基本面条件，获取业绩报表并合并
                fundamental_cond_ids = {"fundamental_revenue", "fundamental_parent_profit", "fundamental_deduct_profit", "fundamental_roe", "fundamental_gross_margin"}
                if any(c.get("type") in fundamental_cond_ids for c in conditions):
                    with st.status("📊 正在获取基本面数据...", expanded=True) as fin_status:
                        fin_report = get_financial_report()
                        if not fin_report.empty:
                            # 避免名称列冲突
                            if "名称" in fin_report.columns:
                                fin_report = fin_report.drop(columns=["名称"])
                            analysis_pool = analysis_pool.merge(fin_report, on="代码", how="left")
                            fin_status.update(label=f"✅ 基本面数据获取完成 ({len(fin_report)}只)")
                        else:
                            fin_status.update(label="⚠️ 基本面数据获取失败，将跳过基本面条件")
                result = func(analysis_pool, klines_dict=klines_dict, conditions=conditions, **extra)
            else:
                result = func(analysis_pool, klines_dict=klines_dict, **extra)
        except Exception as e:
            st.error(f"策略执行出错: {e}")
            st.stop()

        # 补充实时行情列（如果策略结果缺失涨跌幅等常用列）
        if not result.empty and "涨跌幅" not in result.columns and "涨跌幅" in analysis_pool.columns:
            extra_cols = [c for c in ["涨跌幅", "成交量", "换手率", "市盈率", "市净率"] if c in analysis_pool.columns and c not in result.columns]
            if extra_cols:  # 有需要补充的列
                merge_cols = ["代码"] + extra_cols
                result = result.merge(analysis_pool[merge_cols], on="代码", how="left")

    # 缓存结果
    st.session_state.last_result = result
    st.session_state.last_strategy = sel_strategy
    st.session_state.last_params = {
        "min_price": min_price, "max_price": max_price,
        "filter_st": filter_st, "filter_hs": filter_hs,
        "chg_min": chg_min, "chg_max": chg_max,
        "vol_min": vol_min, "vol_max": vol_max,
        "pe_min": pe_min, "pe_max": pe_max,
        "pb_min": pb_min, "pb_max": pb_max,
        **extra,
    }
    st.session_state.klines_cache = klines_dict

    # 截断提示 + 内联调整
    if truncated:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.info(f"ℹ️ 候选股过多，仅分析了换手率最高的 **{max_candidates}** 只股票。如需全量分析，请调高候选股上限或缩小过滤范围。")
        with c2:
            if st.button("⚡ 调整候选股上限", key="btn_toggle_max_slider", width="stretch"):
                st.session_state.show_inline_max_slider = True
                st.rerun()

        if st.session_state.get("show_inline_max_slider", False):
            st.markdown("<div style='background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;margin-bottom:10px;'>", unsafe_allow_html=True)
            new_max = st.slider("候选股上限", 100, 2000, st.session_state.max_candidates, 100, key="slider_inline_max")
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("✅ 确认并重新选股", key="btn_confirm_max", width="stretch"):
                    st.session_state.max_candidates = new_max
                    st.session_state.show_inline_max_slider = False
                    st.session_state.run_trigger = True
                    st.rerun()
            with c2:
                if st.button("❌ 取消", key="btn_cancel_max", width="stretch"):
                    st.session_state.show_inline_max_slider = False
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # 结果显示
    if result.empty:
        st.warning("⚠️ 当前过滤条件下没有选出符合条件的股票，请放宽条件后重试。")
        st.stop()

    result = result.reset_index(drop=True)
    total_val = len(result)
    st.success(f"✅ 选股完成！共选出 **{total_val}** 只符合条件的股票")

# ========== 结果显示（基于缓存，支持 run_trigger=True 和 run_trigger=False）==========
if "last_result" in st.session_state and st.session_state.last_result is not None:
    result = st.session_state.last_result
    sel_strategy = st.session_state.last_strategy

    # 搜索、排序和导出
    col_search, col_sort, col_export = st.columns([2, 1, 1])
    with col_search:
        search_term = st.text_input("🔍 搜索股票（代码/名称）", "", key="search_stock")
    with col_sort:
        sort_options = ["匹配度 ↓", "涨幅 ↓", "涨幅 ↑"]
        sort_by = st.selectbox("排序", sort_options, key="card_sort_by")
    with col_export:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        exp_buf = io.BytesIO()
        with pd.ExcelWriter(exp_buf, engine="openpyxl") as writer:
            result.to_excel(writer, index=False, sheet_name="选股结果")
        st.download_button(
            label="📥 导出Excel", data=exp_buf.getvalue(),
            file_name=f"选股_{datetime.now().strftime('%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch", key="dl_excel"
        )

    # 搜索结果
    if search_term:
        display_df = result[
            result["代码"].astype(str).str.contains(search_term, case=False, na=False) |
            result["名称"].astype(str).str.contains(search_term, case=False, na=False)
        ]
    else:
        display_df = result.copy()

    # 排序
    if sort_by == "匹配度 ↓":
        display_df["_match_score"] = display_df.apply(lambda r: calc_match_score(sel_strategy, r), axis=1)
        display_df = display_df.sort_values("_match_score", ascending=False).drop(columns=["_match_score"])
    elif sort_by == "涨幅 ↓":
        chg_col = "涨跌幅" if "涨跌幅" in display_df.columns else "涨幅%"
        if chg_col in display_df.columns:
            display_df = display_df.sort_values(chg_col, ascending=False)
    elif sort_by == "涨幅 ↑":
        chg_col = "涨跌幅" if "涨跌幅" in display_df.columns else "涨幅%"
        if chg_col in display_df.columns:
            display_df = display_df.sort_values(chg_col, ascending=True)

    # ========== 卡片式结果展示 ==========
    if not st.session_state.show_kline_view:
        # ========== 卡片列表视图 ==========
        CARDS_PER_PAGE = 8

        # 分页状态
        if "card_page" not in st.session_state:
            st.session_state.card_page = 0

        total_cards = len(display_df)
        total_pages = max(1, (total_cards + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)

        # 分页控制
        page_cols = st.columns([1, 2, 1])
        with page_cols[0]:
            if st.button("◀ 上一页", disabled=st.session_state.card_page <= 0, width="stretch", key="btn_prev_page"):
                st.session_state.card_page = max(0, st.session_state.card_page - 1)
                st.rerun()
        with page_cols[1]:
            st.markdown(f"<div style='text-align:center;padding-top:6px;font-size:14px;'>第 {st.session_state.card_page + 1} / {total_pages} 页（共 {total_cards} 只）</div>", unsafe_allow_html=True)
        with page_cols[2]:
            if st.button("下一页 ▶", disabled=st.session_state.card_page >= total_pages - 1, width="stretch", key="btn_next_page"):
                st.session_state.card_page = min(total_pages - 1, st.session_state.card_page + 1)
                st.rerun()

        # 计算当前页范围
        start_idx = st.session_state.card_page * CARDS_PER_PAGE
        end_idx = min(start_idx + CARDS_PER_PAGE, total_cards)

        # 渲染卡片（每行2个）
        for i in range(start_idx, end_idx, 2):
            cols = st.columns(2)
            for j in range(2):
                idx = i + j
                if idx >= end_idx:
                    break
                row = display_df.iloc[idx]
                with cols[j]:
                    # 卡片容器样式
                    st.markdown("""
                    <div style="border:1px solid #e1e4e8;border-radius:10px;padding:14px 16px;margin:6px 0;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                    """, unsafe_allow_html=True)

                    # 头部：代码 + 名称 | 价格 + 涨跌幅
                    h1, h2 = st.columns([3, 2])
                    with h1:
                        st.markdown(f"<span style='font-size:18px;font-weight:800;color:#1565c0;'>{row['代码']}</span> <span style='font-size:17px;font-weight:700;'>{row['名称']}</span>", unsafe_allow_html=True)
                    with h2:
                        price = float(row.get("最新价", 0))
                        chg = float(row.get("涨跌幅", row.get("涨幅%", 0)))
                        chg_color = "#ef5350" if chg >= 0 else "#4caf50"
                        arrow = "▲" if chg >= 0 else "▼"
                        st.markdown(f"<div style='text-align:right;'><div style='font-size:22px;font-weight:800;'>¥{price:.2f}</div><div style='font-size:17px;font-weight:700;color:{chg_color};'>{arrow} {chg:+.2f}%</div></div>", unsafe_allow_html=True)

                    # 匹配度
                    score = calc_match_score(sel_strategy, row)
                    st.progress(score / 100, text=f"⭐ 策略匹配度：{score}%")

                    # 条件 badge 行（默认显示）
                    conditions = get_card_conditions(sel_strategy, row)
                    badges_html = '<div style="display:flex;flex-wrap:wrap;gap:5px;margin:4px 0 8px 0;">'
                    for cond in conditions:
                        badge_color = "#2e7d32" if cond["met"] else "#c62828"
                        bg_color = "#e8f5e9" if cond["met"] else "#ffebee"
                        border_color = "#c8e6c9" if cond["met"] else "#ffcdd2"
                        icon = "✓" if cond["met"] else "✗"
                        badges_html += f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{bg_color};color:{badge_color};font-size:11px;border:1px solid {border_color};font-weight:600;white-space:nowrap;">{cond["name"]} {icon}</span>'
                    badges_html += '</div>'
                    st.markdown(badges_html, unsafe_allow_html=True)

                    # 详细解释（expander）
                    with st.expander("📋 条件详细解释"):
                        for cond in conditions:
                            icon = "✅" if cond["met"] else "❌"
                            color = "#4caf50" if cond["met"] else "#ef5350"
                            st.markdown(f"<span style='color:{color};'>{icon}</span> <b>{cond['name']}</b>", unsafe_allow_html=True)
                            st.caption(cond["detail"])

                    # 迷你走势图（分时优先，非当日 fallback 日K）
                    code = row["代码"]
                    has_chart = False
                    chart_type = ""
                    x_vals = y_vals = None
                    open_p = latest = 0.0

                    if "intraday_cache" not in st.session_state:
                        st.session_state.intraday_cache = {}
                    intraday = st.session_state.intraday_cache.get(code)
                    if intraday is None:
                        intraday = get_intraday(code)
                        st.session_state.intraday_cache[code] = intraday

                    if intraday is not None and not intraday.empty and len(intraday) >= 2:
                        x_vals = intraday["时间"]
                        y_vals = intraday["价格"]
                        open_p = float(y_vals.iloc[0])
                        latest = float(y_vals.iloc[-1])
                        has_chart = True
                        chart_type = "intraday"

                    if not has_chart:
                        kline_df = st.session_state.klines_cache.get(code)
                        if kline_df is not None and not kline_df.empty and len(kline_df) >= 2:
                            mini = kline_df.tail(5).copy()
                            if pd.api.types.is_datetime64_any_dtype(mini["日期"]):
                                x_vals = mini["日期"].dt.strftime("%m-%d")
                            else:
                                x_vals = mini["日期"].astype(str).str[-5:]
                            y_vals = mini["收盘"]
                            open_p = float(y_vals.iloc[0])
                            latest = float(y_vals.iloc[-1])
                            has_chart = True
                            chart_type = "daily"

                    if has_chart and x_vals is not None and y_vals is not None:
                        realtime_chg = float(row.get("涨跌幅", row.get("涨幅%", 0)))
                        realtime_price = float(row.get("最新价", latest))
                        chg_color = "#ef5350" if realtime_chg >= 0 else "#4caf50"
                        # 用实时价校正最终点，避免不同步
                        if abs(latest - realtime_price) > 0.01:
                            latest = realtime_price

                        color = chg_color
                        fill_c = f"rgba(239,83,80,0.08)" if color == "#ef5350" else "rgba(76,175,80,0.08)"
                        pmin = float(y_vals.min())
                        pmax = float(y_vals.max())
                        pr = max(pmax - pmin, open_p * 0.003)
                        y_min = open_p - pr * 0.55
                        y_max = open_p + pr * 0.55

                        n = len(x_vals)
                        tick_vals = [x_vals.iloc[0], x_vals.iloc[n // 2], x_vals.iloc[-1]]
                        tick_texts = ["09:30", "11:30", "15:00"] if chart_type == "intraday" else [str(x_vals.iloc[0]), "", str(x_vals.iloc[-1])]

                        n_ticks = 5
                        price_ticks = [y_min + (y_max - y_min) * i / (n_ticks - 1) for i in range(n_ticks)]

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=x_vals, y=y_vals,
                            mode="lines",
                            name="价格",
                            line=dict(color=color, width=1.5),
                            fill="tozeroy",
                            fillcolor=fill_c,
                            hovertemplate="%{x} &nbsp; ¥%{y:.2f}<extra></extra>",
                        ))
                        fig.add_trace(go.Scatter(
                            x=[x_vals.iloc[-1]], y=[latest],
                            mode="markers",
                            marker=dict(color=color, size=5, symbol="circle", line=dict(color="white", width=1)),
                            hoverinfo="skip",
                            showlegend=False,
                        ))
                        fig.add_hline(
                            y=open_p, line_dash="dash", line_color="rgba(128,128,128,0.45)", line_width=1,
                        )
                        # 最右侧涨跌幅标注（与卡片实时行情同步）
                        fig.add_annotation(
                            x=1.0, y=latest, xref="paper", yref="y",
                            text=f"{realtime_chg:+.2f}%",
                            showarrow=False,
                            font=dict(size=10, color=chg_color),
                            xanchor="left", yanchor="middle",
                            xshift=6,
                        )
                        fig.update_layout(
                            height=150,
                            margin=dict(l=45, r=60, t=5, b=22),
                            xaxis=dict(
                                showgrid=True, gridcolor="rgba(0,0,0,0.04)", gridwidth=0.5,
                                tickmode="array", tickvals=tick_vals, ticktext=tick_texts,
                                tickfont=dict(size=9, color="#999"),
                                showline=True, linecolor="rgba(0,0,0,0.1)", linewidth=0.5,
                            ),
                            yaxis=dict(
                                title=dict(text="价格", font=dict(size=10, color="#999")),
                                side="left",
                                tickmode="array", tickvals=price_ticks,
                                ticktext=[f"{p:.2f}" for p in price_ticks],
                                tickfont=dict(size=9, color="#999"),
                                showgrid=True, gridcolor="rgba(0,0,0,0.04)", gridwidth=0.5,
                                showline=True, linecolor="rgba(0,0,0,0.1)", linewidth=0.5,
                                range=[y_min, y_max],
                            ),
                            plot_bgcolor="#fafbfc",
                            paper_bgcolor="rgba(0,0,0,0)",
                            showlegend=False,
                            hovermode="x unified",
                            dragmode=False,
                        )
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

                    st.markdown("</div>", unsafe_allow_html=True)

        # CSV下载
        csv_buf = io.StringIO()
        display_df.to_csv(csv_buf, index=False)
        st.download_button(
            label="📄 导出CSV", data=csv_buf.getvalue().encode("utf-8-sig"),
            file_name=f"选股_{datetime.now().strftime('%m%d_%H%M')}.csv",
            mime="text/csv", key="dl_csv"
        )

    else:
        # ========== K线图详情视图 ==========
        st.subheader("📈 个股K线详情")

        # 返回按钮
        if st.button("← 返回选股结果", type="secondary", width="stretch", key="btn_back_to_cards"):
            st.session_state.show_kline_view = False
            st.rerun()

        # K线图区域
        st.divider()
        st.subheader("📈 个股K线分析")

        sel_code = st.selectbox(
            "选择股票查看K线图",
            options=result["代码"].tolist(),
            format_func=lambda x: f"{x} {result[result['代码']==x]['名称'].values[0]}",
            key="sel_kline_code"
        )

        if sel_code:
            code = str(sel_code)
            kline_df = st.session_state.klines_cache.get(code)

            if kline_df is None or kline_df.empty:
                st.warning(f"⚠️ {code} 暂无K线数据，尝试单股获取...")
                try:
                    kline_df = get_kline(code, days=120)
                except Exception as e:
                    st.error(f"获取K线失败: {e}")
                st.stop()

            if kline_df is not None and not kline_df.empty:
                kline_df = kline_df.sort_values("日期").reset_index(drop=True)

                # 计算指标
                kline_df = compute_indicators(kline_df)

                fig = make_subplots(
                    rows=5, cols=1, shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=[0.35, 0.15, 0.15, 0.15, 0.20],
                    subplot_titles=("K线 + MA", "成交量", "MACD", "RSI", "KDJ"),
                )

                # K线
                fig.add_trace(go.Candlestick(
                    x=kline_df["日期"], open=kline_df["开盘"], high=kline_df["最高"],
                    low=kline_df["最低"], close=kline_df["收盘"], name="K线",
                ), row=1, col=1)
                for ma, color in [("ma5", "#ff9800"), ("ma10", "#2196f3"), ("ma20", "#9c27b0"), ("ma60", "#4caf50")]:
                    fig.add_trace(go.Scatter(
                        x=kline_df["日期"], y=kline_df[ma], mode="lines",
                        name=ma, line=dict(color=color, width=1),
                    ), row=1, col=1)

                # 成交量
                colors = ["#ef5350" if c >= o else "#66bb6a" for c, o in zip(kline_df["收盘"], kline_df["开盘"])]
                fig.add_trace(go.Bar(
                    x=kline_df["日期"], y=kline_df["成交量"], marker_color=colors, name="成交量",
                ), row=2, col=1)

                # MACD
                fig.add_trace(go.Bar(
                    x=kline_df["日期"], y=kline_df["macd_hist"],
                    marker_color=["#ef5350" if v >= 0 else "#66bb6a" for v in kline_df["macd_hist"]],
                    name="MACD柱",
                ), row=3, col=1)
                fig.add_trace(go.Scatter(
                    x=kline_df["日期"], y=kline_df["macd"], mode="lines",
                    name="DIF", line=dict(color="#2196f3", width=1),
                ), row=3, col=1)
                fig.add_trace(go.Scatter(
                    x=kline_df["日期"], y=kline_df["macd_signal"], mode="lines",
                    name="DEA", line=dict(color="#ff9800", width=1),
                ), row=3, col=1)

                # RSI
                fig.add_trace(go.Scatter(
                    x=kline_df["日期"], y=kline_df["rsi14"], mode="lines",
                    name="RSI14", line=dict(color="#9c27b0", width=1),
                ), row=4, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="#66bb6a", row=4, col=1, annotation_text="超卖")
                fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", row=4, col=1, annotation_text="超买")

                # KDJ
                fig.add_trace(go.Scatter(
                    x=kline_df["日期"], y=kline_df["k"], mode="lines",
                    name="K", line=dict(color="#2196f3", width=1),
                ), row=5, col=1)
                fig.add_trace(go.Scatter(
                    x=kline_df["日期"], y=kline_df["d"], mode="lines",
                    name="D", line=dict(color="#ff9800", width=1),
                ), row=5, col=1)
                fig.add_trace(go.Scatter(
                    x=kline_df["日期"], y=kline_df["j"], mode="lines",
                    name="J", line=dict(color="#9c27b0", width=1),
                ), row=5, col=1)

                fig.update_layout(
                    title=f"{result[result['代码']==code]['名称'].values[0]} ({code}) - K线分析",
                    xaxis_rangeslider_visible=False,
                    height=900, showlegend=True,
                    template="plotly_white",
                    hovermode="x unified",
                )
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.05)")
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.05)")
                st.plotly_chart(fig, use_container_width=True)

                # 当前指标值
                latest = kline_df.iloc[-1]
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("MA5", f"{latest['ma5']:.2f}" if pd.notna(latest.get('ma5')) else "N/A")
                    st.metric("MA10", f"{latest['ma10']:.2f}" if pd.notna(latest.get('ma10')) else "N/A")
                with m2:
                    st.metric("MA20", f"{latest['ma20']:.2f}" if pd.notna(latest.get('ma20')) else "N/A")
                    st.metric("MA60", f"{latest['ma60']:.2f}" if pd.notna(latest.get('ma60')) else "N/A")
                with m3:
                    st.metric("RSI(14)", f"{latest['rsi14']:.1f}" if pd.notna(latest.get('rsi14')) else "N/A")
                    st.metric("MACD", f"{latest['macd']:.3f}" if pd.notna(latest.get('macd')) else "N/A")
                with m4:
                    st.metric("K/D/J", f"{latest['k']:.1f}/{latest['d']:.1f}/{latest['j']:.1f}" if pd.notna(latest.get('k')) else "N/A")
                    st.caption("该解释基于您设定的策略条件自动生成")

        st.stop()

# ========== 无结果时的提示 ==========
if "last_result" not in st.session_state or st.session_state.last_result is None:
    st.info("👆 请在上方配置过滤条件和策略参数后，点击「🚀 执行选股」开始分析。")
