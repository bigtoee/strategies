# 📚 RAG Demo - 通用文档问答

基于检索增强生成（RAG）的简单 Demo，支持上传文档、向量检索、Kimi 大模型生成答案。

## 快速开始

### 1. 准备环境

```bash
python3 -m venv venv_rag
source venv_rag/bin/activate
pip install -r requirements_rag.txt
```

### 2. 运行

```bash
export KIMI_API_KEY="sk-xxx"
streamlit run rag_demo.py
```

浏览器打开 `http://localhost:8501`

## 使用说明

1. **上传文档**：支持 PDF、TXT、MD、CSV、HTML、代码文件等。
2. **左侧配置栏**：
   - **Embedding 模型**：推荐 `auto` 或 `sentence-transformers`。
   - **大模型**：推荐选择 **Kimi**，填写 API Key 后自动生成回答。
   - **切分与检索**：调整文本块大小、重叠大小、检索 Top-K。
3. **提问**：在输入框中输入问题，系统会检索最相关的文档片段并调用 Kimi 生成答案。

## 不联网也能跑

即使没有 Kimi API Key，Demo 也能运行：

- 选择 **仅检索，不调用大模型**，只展示检索到的相关片段。
- Embedding 可选择 **TF-IDF** 或 **简单词袋**，无需下载模型。

## 大模型配置

### Kimi（默认推荐）

在左侧侧边栏：
- LLM 后端选择 **Kimi（Moonshot，推荐）**
- 填写 **Kimi API Key**
- 选择模型（默认 `moonshot-v1-8k`）

也可通过环境变量预设：

```bash
export KIMI_API_KEY="sk-xxx"
streamlit run rag_demo.py
```

### Ollama（本地模型）

```bash
ollama run llama3
# 在另一个终端
streamlit run rag_demo.py
```

然后在左侧选择 **Ollama 本地模型**。

## 常见问题

**Q: 左侧选择 Kimi 后仍提示「未配置大模型」？**  
A: 请确认已填写 Kimi API Key；如当前 Key 无新模型权限，请选择 `moonshot-v1-8k`。

**Q: Embedding 模型下载慢？**  
A: 已在代码中设置 HuggingFace 镜像，或可在运行前执行：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## 项目结构

```
rag/
├── __init__.py      # 包入口
├── loader.py        # 文档加载（PDF/TXT/MD）
├── splitter.py      # 文本切分
├── embeddings.py    # Embedding 模型
├── store.py         # 向量存储与检索
├── llm.py           # LLM 客户端（Kimi / Ollama / Noop）
└── pipeline.py      # RAG 主流程

rag_demo.py          # Streamlit 界面
start_rag_demo.sh    # 一键启动脚本（含公网隧道）
requirements_rag.txt # RAG 专用依赖
RAG_README.md        # 本说明
```
