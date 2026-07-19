# -*- coding: utf-8 -*-
"""
文档加载器：支持 txt / md / pdf
"""
import os
import io
from pathlib import Path


def load_text(file_obj) -> str:
    """加载文本文件（txt / md / csv 等）"""
    if isinstance(file_obj, (str, Path)):
        with open(file_obj, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    # Streamlit UploadedFile
    content = file_obj.read()
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    return content


def load_pdf(file_obj) -> str:
    """加载 PDF，优先使用 PyPDF2，否则尝试 pypdf"""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(file_obj)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        pass

    try:
        import pypdf
        reader = pypdf.PdfReader(file_obj)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        pass

    raise ImportError(
        "读取 PDF 需要 PyPDF2 或 pypdf，请安装：pip install PyPDF2"
    )


def load_document(file_obj, filename: str = "") -> str:
    """根据扩展名自动选择加载器"""
    name = filename or (getattr(file_obj, "name", "") if not isinstance(file_obj, (str, Path)) else str(file_obj))
    ext = os.path.splitext(name)[-1].lower()

    if ext in (".txt", ".md", ".csv", ".json", ".py", ".html", ".rst"):
        return load_text(file_obj)
    if ext == ".pdf":
        return load_pdf(file_obj)
    # 未知类型尝试当文本读
    try:
        return load_text(file_obj)
    except Exception as e:
        raise ValueError(f"不支持的文件类型：{ext}，错误：{e}")
