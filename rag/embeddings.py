# -*- coding: utf-8 -*-
"""
Embedding 模型：支持多种后端，按可用性自动降级
优先级：OpenAI > sentence-transformers > scikit-learn TF-IDF > 简单词袋
"""
import re
import numpy as np


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms


class BaseEmbedder:
    def fit(self, texts: list[str]) -> np.ndarray:
        """基于文档训练/初始化，返回文档向量"""
        raise NotImplementedError

    def transform(self, texts: list[str]) -> np.ndarray:
        """使用已训练的表示转换新文本"""
        raise NotImplementedError

    def embed(self, texts: list[str]) -> np.ndarray:
        """默认等价于 fit_transform"""
        return self.fit(texts)

    def embed_query(self, query: str) -> np.ndarray:
        return self.transform([query])


class SimpleEmbedder(BaseEmbedder):
    """零依赖的简单词袋嵌入，适合快速 Demo。"""

    def __init__(self):
        self.vocab = {}
        self.stopwords = set("的 是 了 在 和 有 我 他 她 它 们 这 那 都 而 及 与 或 一个 可以 我们 你 为 之 也 对 会 要 没有 就 不 但 到 从 将 向 使 被 让 给 来 去 上 下 中 里 前 后 内 外".split())

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]", text.lower())
        return [t for t in tokens if t not in self.stopwords]

    def fit(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            tokens = self._tokenize(text)
            counter = {}
            for t in tokens:
                counter[t] = counter.get(t, 0) + 1
            rows.append(counter)

        all_keys = set()
        for r in rows:
            all_keys.update(r.keys())
        vocab = sorted(all_keys)
        self.vocab = {k: i for i, k in enumerate(vocab)}

        mat = np.zeros((len(rows), len(vocab)), dtype=np.float32)
        for i, r in enumerate(rows):
            for k, v in r.items():
                if k in self.vocab:
                    mat[i, self.vocab[k]] = v
        return _normalize(mat)

    def transform(self, texts: list[str]) -> np.ndarray:
        if not self.vocab:
            return self.fit(texts)
        mat = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for i, text in enumerate(texts):
            for t in self._tokenize(text):
                if t in self.vocab:
                    mat[i, self.vocab[t]] += 1
        return _normalize(mat)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.fit(texts)


class TfidfEmbedder(BaseEmbedder):
    """基于 scikit-learn 的 TF-IDF，效果优于简单词袋。"""

    def __init__(self):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as e:
            raise ImportError("使用 TF-IDF 需要安装 scikit-learn：pip install scikit-learn") from e
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]",
            stop_words=None,
            max_features=10000,
        )
        self.fitted = False

    def fit(self, texts: list[str]) -> np.ndarray:
        vectors = self.vectorizer.fit_transform(texts)
        self.fitted = True
        return vectors.toarray().astype(np.float32)

    def transform(self, texts: list[str]) -> np.ndarray:
        if not self.fitted:
            return self.fit(texts)
        vectors = self.vectorizer.transform(texts)
        return vectors.toarray().astype(np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.fit(texts)


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的语义嵌入。"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError("使用 sentence-transformers 需要安装：pip install sentence-transformers") from e
        self.model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    def transform(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.transform(texts)


class OpenAIEmbedder(BaseEmbedder):
    """基于 OpenAI text-embedding-3-small 的嵌入。"""

    def __init__(self, api_key: str = None, model: str = "text-embedding-3-small", base_url: str = None):
        try:
            import openai
        except ImportError as e:
            raise ImportError("使用 OpenAI Embedding 需要安装：pip install openai") from e
        self.model = model
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def fit(self, texts: list[str]) -> np.ndarray:
        return self.transform(texts)

    def transform(self, texts: list[str]) -> np.ndarray:
        texts = [t if t else " " for t in texts]
        resp = self.client.embeddings.create(input=texts, model=self.model)
        vectors = [item.embedding for item in resp.data]
        return np.array(vectors, dtype=np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.transform(texts)


def get_embedder(engine: str = "auto", **kwargs) -> BaseEmbedder:
    """
    工厂函数，按 engine 名称返回 embedder。
    engine: auto | simple | tfidf | sentence-transformers | openai
    """
    engine = engine.lower().strip()

    if engine == "openai":
        return OpenAIEmbedder(**kwargs)

    if engine == "sentence-transformers":
        return SentenceTransformerEmbedder(**kwargs)

    if engine == "tfidf":
        return TfidfEmbedder()

    if engine == "simple":
        return SimpleEmbedder()

    # auto 模式：按可用性依次尝试
    if engine == "auto":
        # 1. OpenAI（需要显式传入 api_key）
        if kwargs.get("api_key"):
            try:
                return OpenAIEmbedder(**kwargs)
            except Exception:
                pass
        # 2. sentence-transformers
        try:
            return SentenceTransformerEmbedder(kwargs.get("model_name", "all-MiniLM-L6-v2"))
        except Exception:
            pass
        # 3. TF-IDF
        try:
            return TfidfEmbedder()
        except Exception:
            pass
        # 4. 简单词袋兜底
        return SimpleEmbedder()

    raise ValueError(f"未知的 embedding engine: {engine}")
