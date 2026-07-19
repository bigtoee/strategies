# -*- coding: utf-8 -*-
"""
核心数据层 - 优先本地数据，不足时联网补充
- 股票列表: akshare
- 实时行情: 腾讯API (qt.gtimg.cn)
- K线数据: 本地通达信.day文件 + 腾讯API (web.ifzq.gtimg.cn)
- 基本面数据: 东方财富API (push2.eastmoney.com)
"""
import re
import os
import struct
import time
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== 配置 ==========
REQUEST_TIMEOUT = 15
MAX_KLINE_WORKERS = 30
BATCH_QUOTE_SIZE = 800      # 腾讯批量行情每次最多股票数
BATCH_FUND_SIZE = 300       # 东方财富基本面每次最多股票数
BATCH_FUND_WORKERS = 3      # 基本面数据并发线程数（避免过多连接被限流）
HSJDAY_DIR = "./hsjday"     # 本地通达信日K线数据目录

# ========== 工具函数 ==========

def is_hs_stock(code: str) -> bool:
    """是否属于沪深A股"""
    return bool(re.match(r"^(600|601|603|605|688|000|001|002|003|300)\d{3}$", str(code)))


def is_risk_stock(name: str) -> bool:
    """是否为ST、*ST、SST、退市、被警示等风险股票"""
    if not isinstance(name, str):
        return False
    risk_keywords = ["ST", "*ST", "SST", "退市", "风险", "暂停上市", "终止上市", "警示"]
    return any(k in name for k in risk_keywords)


def _to_market_prefix(code: str) -> str:
    """内部代码转腾讯市场前缀: 600519 -> sh600519"""
    code = str(code).strip()
    if code.startswith(("6", "688")):
        return f"sh{code}"
    elif code.startswith(("0", "3", "1", "2")):
        return f"sz{code}"
    return code


def _to_em_secid(code: str) -> str:
    """内部代码转东方财富secid: 600519 -> 1.600519"""
    code = str(code).strip()
    if code.startswith(("6", "688")):
        return f"1.{code}"
    elif code.startswith(("0", "3", "1", "2")):
        return f"0.{code}"
    return code


def _get_tdx_day_path(code: str) -> str:
    """根据股票代码返回本地通达信.day文件路径"""
    code = str(code).strip()
    if code.startswith(("6", "688")):
        return os.path.join(HSJDAY_DIR, "sh", "lday", f"sh{code}.day")
    elif code.startswith(("0", "1", "2", "3")):
        return os.path.join(HSJDAY_DIR, "sz", "lday", f"sz{code}.day")
    else:
        return os.path.join(HSJDAY_DIR, "bj", "lday", f"bj{code}.day")


def read_tdx_day(code: str, days: int = 120) -> pd.DataFrame:
    """
    从本地通达信.day文件读取日K线数据
    返回 DataFrame: 日期, 开盘, 收盘, 最高, 最低, 成交量
    如果本地文件不存在或数据不足，返回空DataFrame
    """
    path = _get_tdx_day_path(code)
    if not os.path.exists(path):
        return pd.DataFrame()
    
    try:
        with open(path, "rb") as f:
            # 读取全部数据
            raw = f.read()
        
        record_size = 32
        num_records = len(raw) // record_size
        
        if num_records == 0:
            return pd.DataFrame()
        
        rows = []
        # 只读取最近 days 条
        start_idx = max(0, num_records - days)
        for i in range(start_idx, num_records):
            rec = raw[i * record_size:(i + 1) * record_size]
            if len(rec) < record_size:
                break
            date, open_p, high, low, close, amount, vol, _ = struct.unpack("<IIIIIIII", rec)
            rows.append({
                "日期": str(date),
                "开盘": open_p / 100.0,
                "收盘": close / 100.0,
                "最高": high / 100.0,
                "最低": low / 100.0,
                "成交量": float(vol),
            })
        
        df = pd.DataFrame(rows)
        df["日期"] = pd.to_datetime(df["日期"], format="%Y%m%d")
        df = df.sort_values("日期").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


# ========== 股票列表 ==========

def get_stock_list() -> pd.DataFrame:
    """获取A股列表，过滤ST/警示股，仅保留沪深。失败时回退到本地缓存。"""
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        df.columns = [c.strip() for c in df.columns]
        rmap = {}
        for c in df.columns:
            if "代码" in c or "code" in c.lower():
                rmap[c] = "代码"
            elif "名称" in c or "name" in c.lower():
                rmap[c] = "名称"
        df = df.rename(columns=rmap)
        df = df[["代码", "名称"]].drop_duplicates().reset_index(drop=True)
        # 过滤ST/警示股
        df = df[~df["名称"].apply(is_risk_stock)].reset_index(drop=True)
        # 仅保留沪深A股
        df = df[df["代码"].apply(is_hs_stock)].reset_index(drop=True)
        # 保存到本地缓存
        try:
            os.makedirs("cache", exist_ok=True)
            df.to_pickle("cache/stock_list.pkl")
        except Exception:
            pass
        return df
    except Exception as e:
        print(f"[!] 获取股票列表失败，尝试本地缓存: {e}")
        try:
            df = pd.read_pickle("cache/stock_list.pkl")
            # 再次过滤（缓存可能是原始数据）
            df = df[~df["名称"].apply(is_risk_stock)].reset_index(drop=True)
            df = df[df["代码"].apply(is_hs_stock)].reset_index(drop=True)
            return df
        except Exception:
            return pd.DataFrame()


# ========== 实时行情 (腾讯API) ==========

def get_realtime_quotes(codes: list) -> pd.DataFrame:
    """
    批量获取实时行情
    codes: list of strings like ['600519', '000001']
    返回 DataFrame: 代码, 名称, 最新价, 昨收, 开盘, 最高, 最低, 成交量, 成交额, 涨跌幅, 换手率, 振幅, 量比, 总股本
    """
    if not codes:
        return pd.DataFrame()
    
    results = []
    # 分批请求，每批不超过 BATCH_QUOTE_SIZE
    for i in range(0, len(codes), BATCH_QUOTE_SIZE):
        batch = codes[i:i + BATCH_QUOTE_SIZE]
        batch_str = ",".join([_to_market_prefix(c) for c in batch])
        url = f"http://qt.gtimg.cn/q={batch_str}"
        try:
            r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "gbk"
            text = r.text
            # 解析返回数据: v_sh600519="1~贵州茅台~600519~...";
            for line in text.split(";"):
                line = line.strip()
                if not line or "v_" not in line:
                    continue
                try:
                    # 提取引号内的内容
                    parts = line.split('"')
                    if len(parts) < 2:
                        continue
                    data = parts[1].split("~")
                    if len(data) < 35:
                        continue
                    
                    name = data[1] if len(data) > 1 else ""
                    code = data[2] if len(data) > 2 else ""
                    price = float(data[3]) if data[3] else None
                    close_yest = float(data[4]) if data[4] else None
                    open_price = float(data[5]) if data[5] else None
                    volume = float(data[6]) if data[6] else None
                    # 字段33=最高, 34=最低 (腾讯字段位置)
                    high = float(data[33]) if len(data) > 33 and data[33] else None
                    low = float(data[34]) if len(data) > 34 and data[34] else None
                    
                    # 涨跌幅计算
                    change_pct = None
                    if price and close_yest and close_yest > 0:
                        change_pct = round((price - close_yest) / close_yest * 100, 2)
                    
                    # 尝试提取换手率、振幅、量比、PE、PB、总股本等
                    turnover = None
                    amplitude = None
                    volume_ratio = None
                    amount = None
                    pe = None
                    pb = None
                    total_shares = None
                    
                    # 腾讯字段位置: [37]=换手率, [46]=PB, [52]=PE, [72]=总股本
                    if len(data) > 37 and data[37]:
                        try:
                            turnover = float(data[37])
                        except:
                            pass
                    if len(data) > 46 and data[46]:
                        try:
                            pb = float(data[46])
                        except:
                            pass
                    if len(data) > 52 and data[52]:
                        try:
                            pe = float(data[52])
                        except:
                            pass
                    if len(data) > 36 and data[36]:
                        try:
                            amount = float(data[36])
                        except:
                            pass
                    if len(data) > 72 and data[72]:
                        try:
                            total_shares = float(data[72])
                        except:
                            pass
                    
                    results.append({
                        "代码": code,
                        "名称": name,
                        "最新价": price,
                        "昨收": close_yest,
                        "开盘": open_price,
                        "最高": high,
                        "最低": low,
                        "成交量": volume,
                        "成交额": amount,
                        "涨跌幅": change_pct,
                        "换手率": turnover,
                        "振幅": amplitude,
                        "量比": volume_ratio,
                        "市盈率": pe,
                        "市净率": pb,
                        "总股本": total_shares,
                    })
                except Exception as e:
                    continue
        except Exception as e:
            print(f"[!] 批量行情请求失败: {e}")
            continue
    
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# ========== K线数据 (腾讯API) ==========

# 全局Session用于K线请求（连接复用）
_kline_session = requests.Session()
_kline_session.headers.update({"User-Agent": "Mozilla/5.0"})

def get_kline(code: str, days: int = 120) -> pd.DataFrame:
    """
    获取单只股票K线（优先本地通达信.day文件，不足时联网补充）
    返回 DataFrame: 日期, 开盘, 收盘, 最高, 最低, 成交量
    """
    # 1. 优先从本地读取
    df_local = read_tdx_day(code, days=days)
    if not df_local.empty and len(df_local) >= days * 0.8:
        return df_local
    
    # 2. 本地数据不足，从腾讯API补充
    market_code = _to_market_prefix(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market_code},day,,,{days},qfq"
    
    for attempt in range(2):
        try:
            r = _kline_session.get(url, timeout=REQUEST_TIMEOUT)
            data = r.json()
            stock_data = data.get("data", {}).get(market_code, {})
            klines = stock_data.get("qfqday", [])
            
            if not klines:
                # API无数据，返回本地数据（即使不足）
                return df_local
            
            rows = []
            for item in klines:
                if len(item) >= 6:
                    rows.append({
                        "日期": item[0],
                        "开盘": float(item[1]),
                        "收盘": float(item[2]),
                        "最高": float(item[3]),
                        "最低": float(item[4]),
                        "成交量": float(item[5]),
                    })
            
            df = pd.DataFrame(rows)
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.sort_values("日期").reset_index(drop=True)
            return df
        except Exception:
            if attempt < 1:
                time.sleep(0.2)
            else:
                # 网络失败，返回本地数据（即使不足）
                return df_local
    return df_local


def batch_get_klines(codes: list, days: int = 120, max_workers: int = MAX_KLINE_WORKERS,
                     progress_callback=None) -> dict:
    """
    批量获取K线：优先本地通达信.day文件，不足时联网补充
    返回 {code: DataFrame}
    """
    if not codes:
        return {}
    
    results = {}
    need_api = []
    total = len(codes)
    completed = 0
    
    # 第1步：优先从本地读取（同步，速度快）
    for code in codes:
        df = read_tdx_day(code, days=days)
        if not df.empty and len(df) >= 30:
            results[code] = df
        else:
            need_api.append(code)
        completed += 1
        if progress_callback:
            progress_callback(completed, total)
    
    # 第2步：本地数据不足的，用腾讯API补充（并发）
    if need_api:
        def fetch_one(code):
            df = get_kline(code, days)
            return code, df
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, c): c for c in need_api}
            for future in as_completed(futures):
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
                try:
                    code, df = future.result()
                    if not df.empty and len(df) >= 30:
                        results[code] = df
                except Exception:
                    pass
    
    return results


# ========== 基本面数据 (东方财富API) ==========

def get_fundamentals(codes: list, progress_callback=None) -> pd.DataFrame:
    """
    批量获取PE/PB等基本面数据（使用东方财富单只详情API，并发优化）
    返回 DataFrame: 代码, 名称, 市盈率, 市净率, 总市值, 流通市值
    """
    if not codes:
        return pd.DataFrame()
    
    fields = "f57,f58,f162,f167,f116,f117"
    results = []
    total = len(codes)
    completed = [0]
    
    def fetch_one(code):
        secid = _to_em_secid(code)
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields={fields}"
        
        for attempt in range(2):
            try:
                r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
                data = r.json()
                d = data.get("data", {})
                
                # PE/PB 需要除以100
                pe = d.get("f162")
                pb = d.get("f167")
                
                result = {
                    "代码": str(d.get("f57", "")),
                    "名称": d.get("f58", ""),
                    "市盈率": pe / 100 if pe is not None else None,
                    "市净率": pb / 100 if pb is not None else None,
                    "总市值": d.get("f116"),
                    "流通市值": d.get("f117"),
                }
                
                completed[0] += 1
                if progress_callback and completed[0] % 50 == 0:
                    progress_callback(completed[0], total)
                
                return result
            except Exception:
                if attempt < 1:
                    time.sleep(0.3)
                else:
                    completed[0] += 1
                    if progress_callback and completed[0] % 50 == 0:
                        progress_callback(completed[0], total)
                    return None
        return None
    
    # 并发获取（控制并发数避免连接问题）
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_one, c) for c in codes]
        for future in as_completed(futures):
            res = future.result()
            if res and res["代码"]:
                results.append(res)
    
    if progress_callback:
        progress_callback(total, total)
    
    if not results:
        return pd.DataFrame()
    
    df = pd.DataFrame(results)
    # 转换数值类型
    for col in ["市盈率", "市净率", "总市值", "流通市值"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_financial_report(report_date: str = None, progress_callback=None) -> pd.DataFrame:
    """
    批量获取业绩报表（东方财富），包含营收、归母净利润、扣非每股收益、ROE、毛利率等。
    report_date: 报告期，如 "2026-03-31"；None 则自动选择最近季度。
    返回 DataFrame: 代码, 名称, 报告期, 营业总收入, 归母净利润, 扣非每股收益, 净资产收益率, 销售毛利率
    """
    if report_date is None:
        # 自动选择最近季度（3/6/9/12 月）
        now = datetime.now()
        year, month = now.year, now.month
        # 如果当前月份 <= 4，最新可用的是上一年年报；<=7 是一季报；<=10 是半年报；否则是三季报
        if month <= 4:
            q_month = "12-31"
            year -= 1
        elif month <= 7:
            q_month = "03-31"
        elif month <= 10:
            q_month = "06-30"
        else:
            q_month = "09-30"
        report_date = f"{year}-{q_month}"

    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    page_size = 500
    all_data = []

    def fetch_page(page):
        params = {
            "sortColumns": "UPDATE_DATE,SECURITY_CODE",
            "sortTypes": "-1,-1",
            "pageSize": page_size,
            "pageNumber": page,
            "reportName": "RPT_LICO_FN_CPD",
            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_MARKET_CODE,REPORTDATE,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT,DEDUCT_BASIC_EPS,WEIGHTAVG_ROE,XSMLL",
            "filter": f"(REPORTDATE='{report_date}')",
        }
        try:
            r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            return r.json()
        except Exception:
            return None

    # 先获取第一页确定总页数
    first = fetch_page(1)
    if not first or not first.get("result"):
        return pd.DataFrame()

    page_num = first["result"].get("pages", 1)
    all_data.extend(first["result"].get("data", []))

    if page_num > 1:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_page, p): p for p in range(2, page_num + 1)}
            for future in as_completed(futures):
                res = future.result()
                if res and res.get("result") and "data" in res["result"]:
                    all_data.extend(res["result"]["data"])
                if progress_callback:
                    progress_callback(len(all_data), page_num * page_size)

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.rename(columns={
        "SECURITY_CODE": "代码",
        "SECURITY_NAME_ABBR": "名称",
        "REPORTDATE": "报告期",
        "TOTAL_OPERATE_INCOME": "营业总收入",
        "PARENT_NETPROFIT": "归母净利润",
        "DEDUCT_BASIC_EPS": "扣非每股收益",
        "WEIGHTAVG_ROE": "净资产收益率",
        "XSMLL": "销售毛利率",
    })

    # 数值转换
    for col in ["营业总收入", "归母净利润", "扣非每股收益", "净资产收益率", "销售毛利率"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 过滤沪深A股
    df = df[df["代码"].apply(is_hs_stock)].copy()
    df = df.reset_index(drop=True)
    return df


# ========== 指标计算 ==========

def calc_ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(window=n).mean()


def calc_macd(s: pd.Series, fast=12, slow=26, signal=9):
    ema_f = s.ewm(span=fast, adjust=False).mean()
    ema_s = s.ewm(span=slow, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig, macd - sig


def calc_rsi(s: pd.Series, period=14) -> pd.Series:
    d = s.diff()
    gain = d.where(d > 0, 0).rolling(window=period).mean()
    loss = (-d.where(d < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n=9, m1=3, m2=3):
    ll = low.rolling(window=n).min()
    hh = high.rolling(window=n).max()
    rsv = (close - ll) / (hh - ll) * 100
    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    return k, d, 3 * k - 2 * d


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为DataFrame计算所有技术指标"""
    df = df.copy()
    df["ma5"] = calc_ma(df["收盘"], 5)
    df["ma10"] = calc_ma(df["收盘"], 10)
    df["ma20"] = calc_ma(df["收盘"], 20)
    df["ma60"] = calc_ma(df["收盘"], 60)
    macd, sig, hist = calc_macd(df["收盘"])
    df["macd"] = macd
    df["macd_signal"] = sig
    df["macd_hist"] = hist
    df["rsi14"] = calc_rsi(df["收盘"], 14)
    k, d, j = calc_kdj(df["最高"], df["最低"], df["收盘"])
    df["k"] = k
    df["d"] = d
    df["j"] = j
    return df


def compute_long_term_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算长周期技术指标（用于高级策略）。
    基于日K线，使用更长的参数近似反映季线/年线尺度：
    - 季线 MACD：参数 (20,40,15)，约对应 60 日周期
    - 年线 MACD：参数 (60,120,40)，约对应 250 日周期
    """
    df = df.copy()
    # 季度尺度 MACD（约 60 日）
    macd_q, sig_q, hist_q = calc_macd(df["收盘"], fast=20, slow=40, signal=15)
    df["macd_q"] = macd_q
    df["macd_signal_q"] = sig_q
    df["macd_hist_q"] = hist_q
    # 年度尺度 MACD（约 250 日）
    macd_y, sig_y, hist_y = calc_macd(df["收盘"], fast=60, slow=120, signal=40)
    df["macd_y"] = macd_y
    df["macd_signal_y"] = sig_y
    df["macd_hist_y"] = hist_y
    return df


# ========== 综合数据获取 ==========

def get_stock_quotes_with_fundamentals(codes: list, include_fundamentals: bool = True,
                                        progress_callback=None) -> pd.DataFrame:
    """
    获取股票实时行情 + 基本面数据
    返回合并后的DataFrame
    """
    # 1. 获取实时行情
    if progress_callback:
        progress_callback(0, 3, "获取实时行情...")
    quotes = get_realtime_quotes(codes)
    
    if quotes.empty:
        return pd.DataFrame()
    
    # 2. 获取基本面数据（可选）
    if include_fundamentals and len(codes) > 0:
        if progress_callback:
            progress_callback(1, 3, "获取基本面数据...")
        fund = get_fundamentals(codes)
        if not fund.empty:
            # 合并，优先使用实时行情的名称和最新价（更及时）
            quotes = quotes.merge(fund[["代码", "市盈率", "市净率", "总市值", "流通市值"]],
                                  on="代码", how="left")
    
    if progress_callback:
        progress_callback(3, 3, "数据获取完成")
    
    return quotes


# ========== 分时数据 ==========

def get_intraday(code: str) -> pd.DataFrame:
    """获取当日分时数据（腾讯API），返回DataFrame包含时间、价格、成交量。非当日数据返回空。"""
    prefix = "sh" if code.startswith(("6", "688")) else "sz" if code.startswith(("0", "3", "1", "2")) else "bj"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={prefix}{code}"
    try:
        resp = requests.get(url, timeout=5).json()
        stock_data = resp["data"][f"{prefix}{code}"]
        data_info = stock_data["data"]
        date_str = data_info.get("date", "")
        if date_str != datetime.now().strftime("%Y%m%d"):
            return pd.DataFrame()
        raw = data_info["data"]
        rows = []
        for line in raw:
            parts = line.split()
            time_str = parts[0]
            price = float(parts[1])
            vol = int(parts[2])
            hour = int(time_str[:2])
            minute = int(time_str[2:4])
            rows.append({"时间": f"{hour:02d}:{minute:02d}", "价格": price, "成交量": vol})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()
