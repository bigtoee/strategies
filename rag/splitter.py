# -*- coding: utf-8 -*-
"""
文本切分器
"""
import re


def recursive_char_splitter(text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> list[str]:
    """
    按字符长度递归切分文本，优先在段落/句子边界处切断。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 5)

    text = re.sub(r"\n+", "\n", text).strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", "。", "？", "！", ".", "?", "!", " ", ""]
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end == len(text):
            chunks.append(text[start:].strip())
            break

        # 从 end 往回找合适的切分点
        split_at = end
        for sep in separators:
            pos = text.rfind(sep, start, end)
            if pos > start + chunk_size // 2:
                split_at = pos + len(sep)
                break

        chunks.append(text[start:split_at].strip())
        start = max(split_at - chunk_overlap, start + 1)

    return [c for c in chunks if c]
