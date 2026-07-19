# 🤖 AI选股系统

高标准A股智能选股工具，基于 SQLite + Pandas向量化计算，选股速度 < 1秒。

## 快速开始

```bash
source venv/bin/activate
streamlit run app.py
```

浏览器打开 `http://localhost:8501`

## 功能特点

| 功能 | 说明 |
|------|------|
| ⚡ 快速体验 | 1-2秒下载测试数据，立即可选股 |
| 🤖 7种策略 | 均线多头、MACD金叉、RSI超卖、量价齐升、突破新高、KDJ金叉、基本面价值 |
| 🚫 风险过滤 | 自动排除ST、*ST、SST、退市、被警示等风险股票 |
| 🇨🇳 市场过滤 | 仅保留沪深A股（主板/中小板/创业板/科创板） |
| 📊 秒级选股 | SQLite本地数据库 + Pandas向量化，全市场 < 1秒 |
| 📈 K线图表 | Plotly五图联动（K线+均线+成交量+MACD+RSI+KDJ） |
| 📥 数据导出 | CSV / Excel 一键下载 |

## 使用流程

1. 打开网页 → 点击左侧「⚡ 快速体验」下载数据（1-2秒）
2. 选择策略 → 调节参数 → 点击「🚀 选股」（秒出结果）
3. 查看结果表格 → 点击个股查看K线图
4. 导出数据

## 选股策略

- **均线多头排列**: 5日>10日>20日>60日
- **MACD金叉**: DIF上穿DEA
- **RSI超卖反弹**: RSI从<30回升
- **量价齐升**: 涨幅>3% + 成交量放大
- **突破新高**: 创N日新高
- **KDJ低位金叉**: K上穿D且K<50
- **基本面价值**: 低PE + 低PB

## RAG Demo

项目同时包含一个**通用文档问答 RAG Demo**：

```bash
python3 -m venv venv_rag
source venv_rag/bin/activate
pip install -r requirements_rag.txt
streamlit run rag_demo.py
```

详细说明见 [RAG_README.md](RAG_README.md)。

## 注意事项

- 默认开启模拟数据模式，确保任何环境下都能运行
- 关闭模拟模式后可获取真实行情数据（需联网）
- 数据仅供研究参考，不构成投资建议
