# -*- coding: utf-8 -*-
"""
选股策略模块 - 基于实时API数据
所有策略接收已过滤的股票DataFrame，按需获取K线进行分析
"""
import pandas as pd
from core import (
    get_kline, batch_get_klines, get_fundamentals,
    calc_ma, calc_macd, calc_rsi, calc_kdj, compute_indicators,
    compute_long_term_indicators,
)

# 策略名称映射
STRATEGY_NAMES = {
    "ma_bull": "均线多头排列",
    "macd_golden": "MACD金叉",
    "rsi_oversold": "RSI超卖反弹",
    "volume_price": "量价齐升",
    "breakout": "突破近期新高",
    "kdj_golden": "KDJ低位金叉",
    "fundamental": "基本面价值",
    "advanced": "高级策略（多条件组合）",
    "nl_custom": "自然语言选股",  # 【新增】
}


# ========== 辅助函数 ==========

def _ensure_klines(codes: list, klines_dict: dict = None, days: int = 120,
                   progress_callback=None) -> dict:
    """确保所有code都有K线数据，没有的自己获取"""
    if klines_dict is None:
        klines_dict = {}
    
    missing = [c for c in codes if c not in klines_dict or klines_dict[c].empty]
    if missing:
        fetched = batch_get_klines(missing, days=days, progress_callback=progress_callback)
        klines_dict.update(fetched)
    
    return klines_dict


def _compute_all_indicators(klines_dict: dict) -> dict:
    """为所有K线数据计算技术指标"""
    result = {}
    for code, df in klines_dict.items():
        if df is None or df.empty or len(df) < 30:
            continue
        try:
            result[code] = compute_indicators(df)
        except Exception:
            pass
    return result


# ========== 策略实现 ==========

def strategy_ma_bull(df: pd.DataFrame, klines_dict: dict = None,
                     min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """均线多头排列: 5日>10日>20日>60日，且股价>MA5"""
    if df.empty:
        return pd.DataFrame()
    
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=120)
    ind_dict = _compute_all_indicators(klines_dict)
    
    results = []
    fail_reason = {}
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in ind_dict:
            fail_reason["no_kline"] = fail_reason.get("no_kline", 0) + 1
            continue
        ind = ind_dict[code]
        if len(ind) < 2:
            continue
        
        latest = ind.iloc[-1]
        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = latest["收盘"]
        
        if not (min_price <= price <= max_price):
            continue
        
        # 均线多头排列
        if (latest["ma5"] > latest["ma10"] > latest["ma20"] > latest["ma60"] and
            price > latest["ma5"]):
            results.append({
                "代码": code,
                "名称": row.get("名称", ""),
                "最新价": round(price, 2),
                "MA5": round(latest["ma5"], 2),
                "MA10": round(latest["ma10"], 2),
                "MA20": round(latest["ma20"], 2),
                "MA60": round(latest["ma60"], 2),
            })
    
    return pd.DataFrame(results)


def strategy_macd_golden(df: pd.DataFrame, klines_dict: dict = None,
                         min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """MACD金叉: 昨日DIF<=DEA，今日DIF>DEA，且MACD柱>0"""
    if df.empty:
        return pd.DataFrame()
    
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=120)
    ind_dict = _compute_all_indicators(klines_dict)
    
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in ind_dict:
            continue
        ind = ind_dict[code]
        if len(ind) < 3:
            continue
        
        today = ind.iloc[-1]
        yest = ind.iloc[-2]
        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = today["收盘"]
        
        if not (min_price <= price <= max_price):
            continue
        
        if (yest["macd"] <= yest["macd_signal"] and
            today["macd"] > today["macd_signal"] and
            today["macd_hist"] > 0):
            results.append({
                "代码": code,
                "名称": row.get("名称", ""),
                "最新价": round(price, 2),
                "MACD": round(today["macd"], 3),
                "MACD_signal": round(today["macd_signal"], 3),
                "MACD_hist": round(today["macd_hist"], 3),
            })
    
    return pd.DataFrame(results)


def strategy_rsi_oversold(df: pd.DataFrame, klines_dict: dict = None,
                          rsi_low=30, rsi_high=45,
                          min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """RSI超卖反弹: RSI从<30回升到30~45"""
    if df.empty:
        return pd.DataFrame()
    
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=120)
    ind_dict = _compute_all_indicators(klines_dict)
    
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in ind_dict:
            continue
        ind = ind_dict[code]
        if len(ind) < 3:
            continue
        
        today = ind.iloc[-1]
        yest = ind.iloc[-2]
        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = today["收盘"]
        
        if not (min_price <= price <= max_price):
            continue
        
        if (yest["rsi14"] < rsi_low and
            rsi_low <= today["rsi14"] <= rsi_high):
            results.append({
                "代码": code,
                "名称": row.get("名称", ""),
                "最新价": round(price, 2),
                "RSI昨日": round(yest["rsi14"], 2),
                "RSI今日": round(today["rsi14"], 2),
            })
    
    return pd.DataFrame(results)


def strategy_volume_price(df: pd.DataFrame, klines_dict: dict = None,
                          min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """量价齐升: 涨幅>3%，成交量>昨日2倍且>20日均量1.5倍"""
    if df.empty:
        return pd.DataFrame()
    
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=30)
    
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in klines_dict:
            continue
        kline = klines_dict[code]
        if len(kline) < 22:
            continue
        
        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = kline.iloc[-1]["收盘"]
        
        if not (min_price <= price <= max_price):
            continue
        
        today = kline.iloc[-1]
        yest = kline.iloc[-2]
        
        change_pct = (today["收盘"] - yest["收盘"]) / yest["收盘"] * 100
        vol_ma20 = kline.iloc[-21:-1]["成交量"].mean()
        vol_ratio = today["成交量"] / yest["成交量"] if yest["成交量"] > 0 else 0
        
        if (change_pct > 3 and
            vol_ratio > 2 and
            today["成交量"] > vol_ma20 * 1.5):
            results.append({
                "代码": code,
                "名称": row.get("名称", ""),
                "最新价": round(price, 2),
                "涨幅%": round(change_pct, 2),
                "量比": round(vol_ratio, 2),
            })
    
    return pd.DataFrame(results)


def strategy_breakout(df: pd.DataFrame, klines_dict: dict = None,
                      days=60, min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """突破近期新高: 今日收盘价创days日新高"""
    if df.empty:
        return pd.DataFrame()
    
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=days + 5)
    
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in klines_dict:
            continue
        kline = klines_dict[code]
        if len(kline) < days + 1:
            continue
        
        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = kline.iloc[-1]["收盘"]
        
        if not (min_price <= price <= max_price):
            continue
        
        today_close = kline.iloc[-1]["收盘"]
        hist_high = kline.iloc[-days-1:-1]["最高"].max()
        
        if today_close > hist_high:
            breakout_pct = (today_close - hist_high) / hist_high * 100
            results.append({
                "代码": code,
                "名称": row.get("名称", ""),
                "最新价": round(price, 2),
                f"{days}日最高": round(hist_high, 2),
                "突破幅度%": round(breakout_pct, 2),
            })
    
    return pd.DataFrame(results)


def strategy_kdj_golden(df: pd.DataFrame, klines_dict: dict = None,
                        min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """KDJ低位金叉: K上穿D，且K<50"""
    if df.empty:
        return pd.DataFrame()
    
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=120)
    ind_dict = _compute_all_indicators(klines_dict)
    
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in ind_dict:
            continue
        ind = ind_dict[code]
        if len(ind) < 3:
            continue
        
        today = ind.iloc[-1]
        yest = ind.iloc[-2]
        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = today["收盘"]
        
        if not (min_price <= price <= max_price):
            continue
        
        if (yest["k"] <= yest["d"] and
            today["k"] > today["d"] and
            today["k"] < 50):
            results.append({
                "代码": code,
                "名称": row.get("名称", ""),
                "最新价": round(price, 2),
                "K": round(today["k"], 2),
                "D": round(today["d"], 2),
                "J": round(today["j"], 2),
            })
    
    return pd.DataFrame(results)


def strategy_fundamental(df: pd.DataFrame, fundamentals: pd.DataFrame = None,
                         max_pe=30, max_pb=3,
                         min_price=2.0, max_price=500.0, **kwargs) -> pd.DataFrame:
    """基本面价值: 低PE + 低PB（使用实时行情中的PE/PB数据）"""
    if df.empty:
        return pd.DataFrame()
    
    merged = df.copy()
    
    # 价格过滤
    merged = merged[(merged["最新价"] >= min_price) & (merged["最新价"] <= max_price)]
    
    # PE过滤（优先使用传入的fundamentals，否则用df中的）
    pe_col = None
    if fundamentals is not None and not fundamentals.empty and "市盈率" in fundamentals.columns:
        # 合并外部基本面数据
        merged = merged.merge(fundamentals[["代码", "市盈率", "市净率", "总市值"]], on="代码", how="left", suffixes=("", "_fund"))
        if "市盈率_fund" in merged.columns:
            merged["市盈率"] = merged["市盈率_fund"].fillna(merged["市盈率"])
            merged["市净率"] = merged["市净率_fund"].fillna(merged["市净率"])
        pe_col = "市盈率"
    elif "市盈率" in merged.columns:
        pe_col = "市盈率"
    
    pb_col = "市净率" if "市净率" in merged.columns else None
    
    if pe_col:
        merged = merged[merged[pe_col] > 0]
        merged = merged[merged[pe_col] <= max_pe]
    
    if pb_col:
        merged = merged[merged[pb_col] > 0]
        merged = merged[merged[pb_col] <= max_pb]
    
    if merged.empty:
        return pd.DataFrame()
    
    # 选择输出列
    cols = ["代码", "名称", "最新价", "涨跌幅", "市盈率", "市净率"]
    avail = [c for c in cols if c in merged.columns]
    result = merged[avail].copy()
    
    return result.reset_index(drop=True)


# ========== 高级策略（多条件组合） ==========

# 高级策略可选条件元数据
# key: 条件ID, name: 显示名称, desc: 说明, need_long: 是否需要长周期指标
ADVANCED_CONDITIONS = {
    "ma_bull": {"name": "均线多头排列", "desc": "日线 MA5 > MA10 > MA20 > MA60 且股价 > MA5"},
    "price_above_ma60": {"name": "股价站上MA60", "desc": "当前价格站在60日均线上方"},
    "macd_golden": {"name": "MACD金叉", "desc": "日线 DIF 上穿 DEA，且 MACD 柱 > 0"},
    "macd_positive": {"name": "日线MACD>0", "desc": "日线 DIF > DEA（MACD柱为正）"},
    "macd_quarterly_positive": {"name": "季线MACD>0", "desc": "季度尺度 MACD > 0（长期趋势向上）"},
    "macd_yearly_positive": {"name": "年线MACD>0", "desc": "年度尺度 MACD > 0（长期趋势向上）"},
    "rsi_oversold": {"name": "RSI超卖反弹", "desc": "RSI 从超卖区回升"},
    "volume_price": {"name": "量价齐升", "desc": "涨幅>3%，成交量显著放大"},
    "breakout": {"name": "突破近期新高", "desc": "收盘价创近期 N 日新高"},
    "kdj_golden": {"name": "KDJ低位金叉", "desc": "K 上穿 D 且 K < 50"},
    "fundamental": {"name": "基本面低估值", "desc": "PE/PB 处于较低水平"},
    "fundamental_revenue": {"name": "营业总收入", "desc": "营业总收入不低于设定阈值（单位：亿元）"},
    "fundamental_parent_profit": {"name": "归母净利润", "desc": "归母净利润不低于设定阈值（单位：亿元）"},
    "fundamental_deduct_profit": {"name": "扣非净利润", "desc": "扣非净利润不低于设定阈值（单位：亿元）"},
    "fundamental_roe": {"name": "净资产收益率", "desc": "ROE 不低于设定阈值（%）"},
    "fundamental_gross_margin": {"name": "销售毛利率", "desc": "销售毛利率不低于设定阈值（%）"},
    "fundamental_pe": {"name": "市盈率PE范围", "desc": "市盈率在设定范围内"},
    "fundamental_pb": {"name": "市净率PB范围", "desc": "市净率在设定范围内"},
}


def _check_advanced_condition(row: pd.Series, ind: pd.DataFrame, kline: pd.DataFrame,
                              cond: dict, **kwargs) -> tuple:
    """
    检查单个高级条件是否满足。
    返回 (是否满足, 结果列字典)
    """
    ctype = cond.get("type", "")
    latest = ind.iloc[-1] if len(ind) > 0 else None
    yest = ind.iloc[-2] if len(ind) > 1 else None
    price = row.get("最新价")
    if price is None or pd.isna(price):
        price = latest["收盘"] if latest is not None else None
    if price is None:
        return False, {}

    if ctype == "ma_bull":
        if (latest["ma5"] > latest["ma10"] > latest["ma20"] > latest["ma60"] and
            price > latest["ma5"]):
            return True, {"MA5": round(latest["ma5"], 2), "MA10": round(latest["ma10"], 2),
                          "MA20": round(latest["ma20"], 2), "MA60": round(latest["ma60"], 2)}
        return False, {}

    if ctype == "price_above_ma60":
        return price > latest["ma60"], {"MA60": round(latest["ma60"], 2)}

    if ctype == "macd_golden":
        if (yest["macd"] <= yest["macd_signal"] and
            latest["macd"] > latest["macd_signal"] and
            latest["macd_hist"] > 0):
            return True, {"MACD": round(latest["macd"], 3),
                          "MACD_signal": round(latest["macd_signal"], 3),
                          "MACD_hist": round(latest["macd_hist"], 3)}
        return False, {}

    if ctype == "macd_positive":
        return (latest["macd"] > latest["macd_signal"] and latest["macd_hist"] > 0), \
               {"MACD": round(latest["macd"], 3), "MACD_signal": round(latest["macd_signal"], 3),
                "MACD_hist": round(latest["macd_hist"], 3)}

    if ctype == "macd_quarterly_positive":
        return latest["macd_q"] > latest["macd_signal_q"], \
               {"MACD_Q": round(latest["macd_q"], 3), "MACD_Q_signal": round(latest["macd_signal_q"], 3)}

    if ctype == "macd_yearly_positive":
        return latest["macd_y"] > latest["macd_signal_y"], \
               {"MACD_Y": round(latest["macd_y"], 3), "MACD_Y_signal": round(latest["macd_signal_y"], 3)}

    if ctype == "rsi_oversold":
        rsi_low = kwargs.get("rsi_low", 30)
        rsi_high = kwargs.get("rsi_high", 45)
        if (yest["rsi14"] < rsi_low and rsi_low <= latest["rsi14"] <= rsi_high):
            return True, {"RSI昨日": round(yest["rsi14"], 2), "RSI今日": round(latest["rsi14"], 2)}
        return False, {}

    if ctype == "volume_price":
        if len(kline) < 22:
            return False, {}
        today = kline.iloc[-1]
        yest_k = kline.iloc[-2]
        change_pct = (today["收盘"] - yest_k["收盘"]) / yest_k["收盘"] * 100
        vol_ma20 = kline.iloc[-21:-1]["成交量"].mean()
        vol_ratio = today["成交量"] / yest_k["成交量"] if yest_k["成交量"] > 0 else 0
        if (change_pct > 3 and vol_ratio > 2 and today["成交量"] > vol_ma20 * 1.5):
            return True, {"涨幅%": round(change_pct, 2), "量比": round(vol_ratio, 2)}
        return False, {}

    if ctype == "breakout":
        days = kwargs.get("breakout_days", 60)
        if len(kline) < days + 1:
            return False, {}
        today_close = kline.iloc[-1]["收盘"]
        hist_high = kline.iloc[-days-1:-1]["最高"].max()
        if today_close > hist_high:
            breakout_pct = (today_close - hist_high) / hist_high * 100
            return True, {f"{days}日最高": round(hist_high, 2), "突破幅度%": round(breakout_pct, 2)}
        return False, {}

    if ctype == "kdj_golden":
        if (yest["k"] <= yest["d"] and latest["k"] > latest["d"] and latest["k"] < 50):
            return True, {"K": round(latest["k"], 2), "D": round(latest["d"], 2), "J": round(latest["j"], 2)}
        return False, {}

    if ctype == "fundamental":
        max_pe = kwargs.get("max_pe", 30)
        max_pb = kwargs.get("max_pb", 3)
        pe = row.get("市盈率")
        pb = row.get("市净率")
        if pd.notna(pe) and pd.notna(pb) and pe > 0 and pb > 0 and pe <= max_pe and pb <= max_pb:
            return True, {"市盈率": round(pe, 2), "市净率": round(pb, 2)}
        return False, {}

    # 基本面专业指标（基于业绩报表）
    if ctype == "fundamental_revenue":
        min_rev = cond.get("min", kwargs.get("revenue_min", 0.0))  # 亿元
        max_rev = cond.get("max", kwargs.get("revenue_max", 100000.0))
        revenue = row.get("营业总收入")
        if pd.notna(revenue) and min_rev * 1e8 <= revenue <= max_rev * 1e8:
            return True, {"营业总收入(亿)": round(revenue / 1e8, 2)}
        return False, {}

    if ctype == "fundamental_parent_profit":
        min_profit = cond.get("min", kwargs.get("parent_profit_min", 0.0))
        max_profit = cond.get("max", kwargs.get("parent_profit_max", 100000.0))
        profit = row.get("归母净利润")
        if pd.notna(profit) and min_profit * 1e8 <= profit <= max_profit * 1e8:
            return True, {"归母净利润(亿)": round(profit / 1e8, 4)}
        return False, {}

    if ctype == "fundamental_deduct_profit":
        min_profit = cond.get("min", kwargs.get("deduct_profit_min", 0.0))
        max_profit = cond.get("max", kwargs.get("deduct_profit_max", 100000.0))
        deduct_eps = row.get("扣非每股收益")
        total_shares = row.get("总股本")
        if pd.notna(deduct_eps) and pd.notna(total_shares) and total_shares > 0:
            deduct_profit = deduct_eps * total_shares
            if min_profit * 1e8 <= deduct_profit <= max_profit * 1e8:
                return True, {"扣非净利润(亿)": round(deduct_profit / 1e8, 4)}
        return False, {}

    if ctype == "fundamental_roe":
        min_roe = cond.get("min", kwargs.get("roe_min", 0.0))
        max_roe = cond.get("max", kwargs.get("roe_max", 1000.0))
        roe = row.get("净资产收益率")
        if pd.notna(roe) and min_roe <= roe <= max_roe:
            return True, {"净资产收益率": round(roe, 2)}
        return False, {}

    if ctype == "fundamental_gross_margin":
        min_gm = cond.get("min", kwargs.get("gross_margin_min", 0.0))
        max_gm = cond.get("max", kwargs.get("gross_margin_max", 100.0))
        gm = row.get("销售毛利率")
        if pd.notna(gm) and min_gm <= gm <= max_gm:
            return True, {"销售毛利率": round(gm, 2)}
        return False, {}

    if ctype == "fundamental_pe":
        pe = row.get("市盈率")
        if pd.notna(pe) and pe > 0:
            min_pe = cond.get("min", kwargs.get("pe_min", 0.0))
            max_pe = cond.get("max", kwargs.get("pe_max", 500.0))
            if min_pe <= pe <= max_pe:
                return True, {"市盈率": round(pe, 2)}
        return False, {}

    if ctype == "fundamental_pb":
        pb = row.get("市净率")
        if pd.notna(pb) and pb > 0:
            min_pb = cond.get("min", kwargs.get("pb_min", 0.0))
            max_pb = cond.get("max", kwargs.get("pb_max", 50.0))
            if min_pb <= pb <= max_pb:
                return True, {"市净率": round(pb, 2)}
        return False, {}

    return False, {}


def strategy_advanced(df: pd.DataFrame, klines_dict: dict = None,
                      conditions: list = None,
                      min_price=2.0, max_price=500.0,
                      **kwargs) -> pd.DataFrame:
    """
    高级策略：多条件自由组合选股。
    conditions: 条件列表，例如 [{"type": "ma_bull"}, {"type": "macd_yearly_positive"}]
    """
    if df.empty or not conditions:
        return pd.DataFrame()

    # 至少需要250日数据来支持年线指标
    codes = df["代码"].tolist()
    klines_dict = _ensure_klines(codes, klines_dict, days=250)

    # 计算指标（日线 + 长周期）
    ind_dict = {}
    for code, kline in klines_dict.items():
        if kline is None or len(kline) < 160:  # 年线MACD需要约160日
            continue
        try:
            ind = compute_indicators(kline)
            ind = compute_long_term_indicators(ind)
            ind_dict[code] = ind
        except Exception:
            continue

    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code not in ind_dict:
            continue
        ind = ind_dict[code]
        kline = klines_dict[code]
        if len(ind) < 3:
            continue

        price = row.get("最新价")
        if price is None or pd.isna(price):
            price = ind.iloc[-1]["收盘"]
        if not (min_price <= price <= max_price):
            continue

        # 检查所有条件
        all_met = True
        detail_cols = {"代码": code, "名称": row.get("名称", ""), "最新价": round(price, 2)}
        for cond in conditions:
            met, cols = _check_advanced_condition(row, ind, kline, cond, **kwargs)
            if not met:
                all_met = False
                break
            detail_cols.update(cols)

        if all_met:
            results.append(detail_cols)

    return pd.DataFrame(results)


def strategy_nl_custom(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    自然语言自定义选股策略。
    这个策略本身不做任何过滤，因为过滤逻辑已在 app.py 中处理。
    这里只是返回传入的 DataFrame（已经过滤后的结果）。
    """
    # 自然语言条件已在 app.py 中应用，这里直接返回
    # 但为了结果一致性，我们添加一些基本信息列
    if df.empty:
        return pd.DataFrame()
    
    # 确保有必要的列
    result_cols = ["代码", "名称", "最新价", "涨跌幅"]
    for col in result_cols:
        if col not in df.columns:
            if col == "涨跌幅":
                df["涨跌幅"] = 0.0
            elif col == "最新价":
                df["最新价"] = 0.0
    
    return df.copy()


# 策略注册表
STRATEGIES = {
    "ma_bull": strategy_ma_bull,
    "macd_golden": strategy_macd_golden,
    "rsi_oversold": strategy_rsi_oversold,
    "volume_price": strategy_volume_price,
    "breakout": strategy_breakout,
    "kdj_golden": strategy_kdj_golden,
    "fundamental": strategy_fundamental,
    "advanced": strategy_advanced,
    "nl_custom": strategy_nl_custom,  # 【新增】自然语言选股
}
