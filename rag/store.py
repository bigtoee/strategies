# -*- coding: utf-8 -*-
"""
简单向量存储：基于 NumPy 的 cosine similarity Top-K 检索
"""
import numpy as np


class VectorStore:
    def __init__(self):
        self.vectors = None
        self.texts = []
        self.metadatas = []

    def add(self, texts: list[str], vectors: np.ndarray, metadatas: list[dict] = None):
        """添加文档块及其向量"""
        if len(texts) != vectors.shape[0]:
            raise ValueError("texts 数量与 vectors 行数不一致")

        self.texts.extend(texts)
        self.metadatas.extend(metadatas or [{} for _ in texts])

        if self.vectors is None:
            self.vectors = vectors.copy()
        else:
            self.vectors = np.vstack([self.vectors, vectors])

    def similarity_search(self, query_vector: np.ndarray, k: int = 4) -> list[dict]:
        """返回最相关的 k 个文档块"""
        if self.vectors is None or len(self.texts) == 0:
            return []

        query_vector = np.array(query_vector).reshape(1, -1)
        # cosine similarity = dot product of normalized vectors
        scores = (self.vectors @ query_vector.T).flatten()
        top_k = min(k, len(self.texts))
        indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in indices:
            results.append({
                "text": self.texts[idx],
                "metadata": self.metadatas[idx],
                "score": float(scores[idx]),
            })
        return results

    def clear(self):
        self.vectors = None
        self.texts = []
        self.metadatas = []

    def __len__(self):
        return len(self.texts)
